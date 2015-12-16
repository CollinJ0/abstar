#!/usr/bin/python
# filename: vdj.py

#
# Copyright (c) 2015 Bryan Briney
# License: The MIT license (http://opensource.org/licenses/MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software
# and associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute,
# sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#


from __future__ import print_function

import os
import re
import sys
import logging
import platform
import tempfile
import traceback

from Bio import SeqIO
from Bio.Blast.Applications import NcbiblastnCommandline
from Bio.Blast import NCBIXML
from Bio.Seq import Seq
from Bio.Alphabet import generic_dna

from abstar.ssw.ssw_wrap import Aligner
from abstar.utils.queue.celery import celery
from abstar.utils.sequence import Sequence


class VDJ(object):
	'''
	Data structure for managing germline gene assignments for a single antibody sequence.

	Input is a Sequence object, V and J BlastResult objects, and (optionally) a
	DiversityResult object.

	VDJ objects without an identified V or J gene will have 'None' for the unidentified gene
	segment and the 'rearrangement' attribute will be False.
	'''
	def __init__(self, seq, args, v, j, d=None):
		super(VDJ, self).__init__()
		self.id = seq.id
		self.raw_input = seq.sequence
		self.raw_query = seq.input
		self.uaid = seq.input[:args.uaid] if args.uaid else ''
		self.strand = seq.strand
		self._isotype = args.isotype
		self.v = v
		self.j = j
		self.d = d
		if v and j:
			try:
				self.rearrangement = True
				self._get_attributes()
			except:
				self.rearrangement = False
				logging.info('VDJ ATTRIBUTE ERROR: {}'.format(seq.id))
				logging.debug(traceback.format_exc())
		else:
			if not v:
				logging.debug('V ASSIGNMENT ERROR: {}'.format(seq.id))
			if not j:
				logging.debug('J ASSIGNMENT ERROR: {}'.format(seq.id))
			self.rearrangement = False


	def _get_attributes(self):
		'Adds VDJ attributes, only for VDJ objects with an identified V and J gene.'
		self.species = self.v.species
		self.chain = self._get_chain()
		self.query_reading_frame = self._query_reading_frame()
		self.v_start = self._get_v_start()
		self.v_end = self._get_v_end()
		self.j_start = self._get_j_start()
		self.j_end = self._get_j_end()
		if self.d:
			self.d_start = self._get_d_start()
			self.d_end = self._get_d_end()
			self.n1_start = self._get_n1_start()
			self.n1_end = self._get_n1_end()
			self.n2_start = self._get_n2_start()
			self.n2_end = self._get_n2_end()
			self.n_start = None
			self.n_end = None
		else:
			self.d_start = None
			self.d_end = None
			self.n1_start = None
			self.n1_end = None
			self.n2_start = None
			self.n2_end = None
			self.n_start = self._get_n_start()
			self.n_end = self._get_n_end()

		self.vdj_region_string = self._get_vdj_region_string()
		self.vdj_nt = self._vdj_nt()
		self.vdj_aa = self._vdj_aa()
		self.junction = self._get_junction()
		self.productive = self._check_productivity()
		if self._isotype:
			from abstar.utils.isotype import get_isotype
			self.isotype = get_isotype(self)
		else:
			self.isotype = ''
		if not self.junction:
			self.rearrangement = False



	def _get_chain(self):
		'Returns the antibody chain.'
		try:
			if self.v.top_germline.startswith('IGH'):
				return 'heavy'
			elif self.v.top_germline.startswith('IGK'):
				return 'kappa'
			elif self.v.top_germline.startswith('IGL'):
				return 'lambda'
		except:
			logging.debug('GET CHAIN ERROR: {}, {}'.format(self.id,
														   self.v.top_germline))
			return ''

	def _query_reading_frame(self):
		'Returns the reading frame of the query sequence.'
		try:
			return self.v.germline_start % 3
		except:
			logging.debug('QUERY READING FRAME ERROR: {}, {}'.format(self.id,
																	 self.v.germline_start))

	def _vdj_nt(self):
		'Returns the nucleotide sequence of the VDJ region.'
		try:
			vdj_nt = self.v.query_alignment + \
				self.j.input_sequence[:self.j.query_start + len(self.j.query_alignment)]
			return vdj_nt.replace('-', '')
		except:
			logging.debug('VDJ NT ERROR: {}, {}'.format(self.id, self.raw_query))

	def _vdj_aa(self):
		'Returns the amino acid sequence of the VDJ region.'
		offset = (self.query_reading_frame * 2) % 3
		trim = len(self.vdj_nt) - (len(self.vdj_nt[offset:]) % 3)
		translated_seq = Seq(self.vdj_nt[offset:trim], generic_dna).translate()
		return str(translated_seq)

	def _get_junction(self):
		from abstar.utils import junction
		return junction.get_junction(self)

	def _get_v_start(self):
		return self.v.query_start

	def _get_v_end(self):
		return len(self.v.query_alignment)

	def _get_j_start(self):
		return self.v_end + self.j.query_start

	def _get_j_end(self):
		return self.j_start + len(self.j.query_alignment)

	def _get_n1_start(self):
		return self.v_end + 1

	def _get_n1_end(self):
		return self.d_start

	def _get_d_start(self):
		return self.v_end + self.d.query_start

	def _get_d_end(self):
		return self.d_start + len(self.d.query_alignment)

	def _get_n2_start(self):
		return self.d_end + 1

	def _get_n2_end(self):
		return self.j_start

	def _get_n_start(self):
		return self.v_end + 1

	def _get_n_end(self):
		return self.j_start

	def _get_vdj_region_string(self):
		region_string = ''
		region_string += 'V' * self.v_end
		if self.d:
			region_string += 'N' * (self.d_start - self.v_end)
			region_string += 'D' * (self.d_end - self.d_start)
			region_string += 'N' * (self.j_start - self.d_end)
		else:
			region_string += 'N' * (self.j_start - self.v_end)
		region_string += 'J' * (self.j_end - self.j_start)
		return region_string

	def _check_productivity(self):
		from abstar.utils import productivity
		return productivity.check_productivity(self)


	def _build_output(self, output_type):
		from abstar.utils import output
		return output.build_output(self, output_type)


class NullVDJ(object):
	'''
	Structure for holding a sequence that didn't pass quality checks.
	Essentailly it's an indicator for downstream operations that a
	rearrangement wasn't identified.
	'''
	def __init__(self):
		self.rearrangement = False


class Alignment(object):
	'''
	Data structure to hold the result of a SSW local alignment. Parses the
	raw data from the output of a ssw.Aligner alignment (a PyAlignRes object)
	into something more useful.

	Input is the ID of the top-scoring target, the query sequence, the target
	sequence and the PyAlignRes object.
	'''
	def __init__(self, target_id, query_seq, target_seq, alignment):
		super(Alignment, self).__init__()
		self.target_id = target_id
		self.query_seq = query_seq
		self.target_seq = target_seq
		self.alignment = alignment
		self.cigar = alignment.cigar_string
		self.query_begin = alignment.ref_begin
		self.query_end = alignment.ref_end + 1
		self.target_begin = alignment.query_begin
		self.target_end = alignment.query_end + 1
		self.aligned_query = self._get_aligned_query()
		self.aligned_target = self._get_aligned_target()

	def _get_aligned_query(self):
		'Returns the aligned portion of the query sequence'
		return self.query_seq[self.query_begin:self.query_end]

	def _get_aligned_target(self):
		'Returns the aligned portion of the target sequence'
		return self.target_seq[self.target_begin:self.target_end]



class BlastResult(object):
	'''
	Data structure for parsing and holding a BLASTn result.
	Input is a file handle for the XML-formatted BLASTn output file.
	'''
	def __init__(self, seq_id, blastout, input_sequence, species):
		super(BlastResult, self).__init__()
		self.id = seq_id
		self.alignments = blastout.alignments
		self.input_sequence = input_sequence
		self.species = species
		self.top_germline = self._get_top_germline()
		self.all_germlines = self._get_all_germlines()
		self.top_score = self._get_top_score()
		self.all_scores = self._get_all_scores()
		self.top_evalue = self._get_top_evalue()
		self.all_evalues = self._get_all_evalues()
		self.top_bitscore = self._get_top_bitscore()
		self.all_bitscores = self._get_all_bitscores()
		self.strand = 'plus'
		self.query_alignment = self._get_query_alignment()
		self.germline_alignment = self._get_germline_alignment()
		self.alignment_midline = self._get_alignment_midline()
		self.alignment_length = self._get_alignment_length()
		self.query_start = self._get_query_start()
		self.query_end = self._get_query_end()
		self.germline_start = self._get_germline_start()
		self.germline_end = self._get_germline_end()
		self.gene_type = self._gene_type()
		self.chain = self._chain()

	def annotate(self):
		self.fs_indel_adjustment = 0
		self.nfs_indel_adjustment = 0
		self._find_indels()
		self.regions = self._regions()
		self.nt_mutations = self._nt_mutations()
		self.aa_mutations = self._aa_mutations()


	def realign_joining(self, germline_gene):
		'''
		Due to restrictions on the available scoring parameters in BLASTn, incorrect annotation of
		indels in the j-gene alignment can occur. This function re-aligns the query sequence with
		the identified germline joining gene using more appropriate alignment parameters.

		Input is the name of the germline joining gene (ex: 'IGHJ6*02').
		'''
		self.germline_seq = self._get_germline_sequence_for_realignment(germline_gene, 'J')
		# ssw = Aligner(self.input_sequence,
		ssw = Aligner(self.input_sequence[self.query_start:],
					  match=3,
					  mismatch=2,
				  	  gap_open=12,
				  	  gap_extend=1,
				  	  report_cigar=True)
		alignment = ssw.align(self.germline_seq[self.germline_start:])
		self._process_realignment(Alignment(germline_gene,
											self.input_sequence[self.query_start:],
											self.germline_seq[self.germline_start:], alignment))


	def realign_variable(self, germline_gene):
		'''
		Due to restrictions on the available scoring parameters in BLASTn, incorrect truncation
		of the v-gene alignment can occur. This function re-aligns the query sequence with
		the identified germline variable gene using more appropriate alignment parameters.

		Input is the name of the germline variable gene (ex: 'IGHV1-2*02').
		'''
		self.germline_seq = self._get_germline_sequence_for_realignment(germline_gene, 'V')
		ssw = Aligner(self.input_sequence,
					  match=3,
					  mismatch=2,
				  	  gap_open=22,
				  	  gap_extend=1,
				  	  report_cigar=True)
		alignment = ssw.align(self.germline_seq)
		rc = str(Seq(self.input_sequence, generic_dna).reverse_complement())
		ssw_rc = Aligner(rc,
						 match=3,
						 mismatch=2,
						 gap_open=22,
						 gap_extend=1,
						 report_cigar=True)
		alignment_rc = ssw_rc.align(self.germline_seq)
		if alignment.score > alignment_rc.score:
			self._process_realignment(Alignment(germline_gene, self.input_sequence, self.germline_seq, alignment))
		else:
			self.strand = 'minus'
			self.input_sequence = rc
			self._process_realignment(Alignment(germline_gene, self.input_sequence, self.germline_seq, alignment_rc))

	def _get_germline_sequence_for_realignment(self, germ, gene):
		'''
		Identifies the appropriate germline variable gene from a database of all
		germline variable genes.

		Input is the name of the germline variable gene (ex: 'IGHV1-2*02').

		Output is the germline sequence.
		'''
		mod_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		db_file = os.path.join(mod_dir, 'ssw/dbs/{}_{}.fasta'.format(self.species.lower(), gene))
		for s in SeqIO.parse(open(db_file), 'fasta'):
			if s.id == germ:
				return str(s.seq)
		return None

	def _process_realignment(self, alignment):
		'''
		Processes the result of variable gene realignment and updates BlastResult
		attributes accordingly.

		Input is an Alignment object.
		'''
		self.query_alignment, self.germline_alignment = self._cigar_to_alignment(alignment)
		self.alignment_midline = self._get_realignment_midline()
		if self.gene_type == 'variable':
			self.query_start = alignment.query_begin
			self.germline_start = alignment.target_begin
		self.query_end = alignment.query_end
		self.germline_end = alignment.target_end


	def _cigar_to_alignment(self, alignment):
		'''
		Converts the cigar string and aligned region from the query and target
		sequences into a gapped alignment.

		Input is an Alignment object.

		Output is a gapped query sequence and a gapped target sequence.
		'''
		query = ''
		germline = ''
		pattern = re.compile('([MIDNSHPX=])')
		values = pattern.split(alignment.cigar)[:-1]
		pairs = zip(*2*[iter(values)])
		for p in pairs:
			query, germline = self._alignment_chunk_from_cigar_pair(alignment,
																	p,
																	query,
																	germline)
		return query, germline

	def _alignment_chunk_from_cigar_pair(self, alignment, pair, query, germline):
		'''
		Processes a single 'pair' of a cigar string and lengthens the gapped query
		and targed alignment strings.

		Input is an Alignment object, the cigar pair, the partial gapped alignment
		strings for the query and target. If 30M3I250M were to be a cigar string,
		it would have three pairs -- (30, 'M'), (3, 'I') and (250, 'M') --
		which are each formatted as tuples.

		Output is a gapped query alignment and gapped germline alignment that incorporate
		the data from the given cigar string.
		'''
		q = len(query.replace('-', ''))
		g = len(germline.replace('-', ''))
		clength = int(pair[0])
		ctype = pair[1]
		if ctype.upper() == 'S':
			return query, germline
		if ctype.upper() == 'M':
			query += alignment.aligned_query[q:q + clength]
			germline += alignment.aligned_target[g:g + clength]
		elif ctype.upper() == 'D':
			query += alignment.aligned_query[q:q + clength]
			germline += '-' * clength
		elif ctype.upper() == 'I':
			query += '-' * clength
			germline += alignment.aligned_target[g:g + clength]
		return query, germline


	def _find_indels(self):
		'''
		Identifies and annotates indels in the query sequence.
		'''
		self.insertions = []
		self.deletions = []
		if self._indel_check():
			from abstar.utils import indels
			self.insertions = indels.find_insertions(self)
			self.deletions = indels.find_deletions(self)

	def _indel_check(self):
		'''
		Checks the sequence for evidence of insertions or deletions.
		'''
		if '-' in self.query_alignment:
			return True
		elif '-' in self.germline_alignment:
			return True
		return False

	def _regions(self):
		'''
		Identifies and annotates variable/joining gene regions.
		'''
		from abstar.utils import regions
		return regions.regions(self)

	def _nt_mutations(self):
		'''
		Identifies and annotates nucleotide mutations.
		'''
		from abstar.utils import mutations
		return mutations.nt_mutations(self)

	def _aa_mutations(self):
		'''
		Identifies and annotates amino acid mutations.
		'''
		from abstar.utils import mutations
		return mutations.aa_mutations(self)

	def _get_top_germline(self):
		'Returns the top scoring germline gene'
		return self.alignments[0].title.split()[0]

	def _get_all_germlines(self):
		'Returns all germline genes'
		return [alignment.title.split()[0] for alignment in self.alignments]

	def _get_top_score(self):
		'Returns the score for the top scoring germline gene'
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].score

	def _get_all_scores(self):
		'Returns all germline gene scores'
		return [alignment.hsps[0].score for alignment in self.alignments]

	def _get_top_evalue(self):
		'Returns the e-value for the top scoring germline gene'
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].expect

	def _get_all_evalues(self):
		return [alignment.hsps[0].expect for alignment in self.alignments]

	def _get_top_bitscore(self):
		'Returns the bitscore for the top scoring germline gene'
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].bits

	def _get_all_bitscores(self):
		return [alignment.hsps[0].bits for alignment in self.alignments]

	def _get_strand(self):
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].strand

	def _get_query_alignment(self):
		'''Returns the query alignment string for the
		top scoring germline gene alignment'''
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].query

	def _get_germline_alignment(self):
		'Returns the top scoring germline alignment'
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].sbjct

	def _get_alignment_midline(self):
		'''Returns the alignment midline string for the
		top scoring germline gene alignment'''
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].match

	def _get_realignment_midline(self):
		'''Returns the alignment midline string for variable gene realignment'''
		length = min(len(self.query_alignment), len(self.germline_alignment))
		query = self.query_alignment
		germ = self.germline_alignment
		midline = ['|' if query[i] == germ[i] else ' ' for i in range(length)]
		return ''.join(midline)

	def _get_alignment_length(self):
		'Returns the alignment length for the top scoring germline gene alignment'
		return self.alignments[0].length

	def _get_query_start(self):
		'''Returns the start position of the query alignment with
		the top germline gene'''
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].query_start - 1

	def _get_query_end(self):
		'''Returns the start position of the query alignment with
		the top germline gene'''
		return self.query_start + self.alignment_length

	def _get_germline_start(self):
		'Returns the start position of the top germline alignment'
		top_alignment = self.alignments[0]
		return top_alignment.hsps[0].sbjct_start - 1

	def _get_germline_end(self):
		'Returns the end position of the top germline alignment'
		return self.germline_start + self.alignment_length

	def _gene_type(self):
		"Returns the gene type, either 'variable' or 'joining'"
		if self.top_germline[3] == 'V':
			return 'variable'
		elif self.top_germline[3] == 'J':
			return 'joining'
		return None

	def _chain(self):
		'Returns the chain type'
		if self.top_germline.startswith('IGH'):
			return 'heavy'
		elif self.top_germline.startswith('IGK'):
			return 'kappa'
		elif self.top_germline.startswith('IGL'):
			return 'lambda'
		# hack to accomodate IgBLAST's crappy germline database
		# to be removed when I curate the database
		elif self.top_germline.startswith('VH'):
			return 'heavy'
		return None



class DiversityResult(object):
	"""
	Data structure for holding information about diversity germline gene assignments.
	Designed to have (mostly) the same attributes as BlastResult objects, so that
	DiversityResult objects and BlastResult objects can (mostly) be used
	interchangeably in downstream operations.

	Main differences between DiversityResult and BlastResult are that DiversityResults
	have empty bitscore and e-value attributes, and the alignments attribute contains
	an Alignment object instead of parsed BLASTn output.

	Input is a list of Alignment objects, representing the top-scoring diversity genes.
	"""
	def __init__(self, seq_id, seq, alignments):
		super(DiversityResult, self).__init__()
		self.id = seq_id
		self.input_sequence = seq
		self.alignments = alignments
		self.top_germline = self._get_top_germline()
		self.all_germlines = self._get_all_germlines()
		self.top_score = self._get_top_score()
		self.all_scores = self._get_all_scores()
		self.top_evalue = None
		self.all_evalues = []
		self.top_bitscore = None
		self.all_bitscores = []
		self.query_alignment = self._get_query_alignment()
		self.germline_alignment = self._get_germline_alignment()
		self.alignment_midline = self._get_alignment_midline()
		self.alignment_length = self._get_alignment_length()
		self.query_start = self._get_query_start()
		self.query_end = self._get_query_end()
		self.germline_start = self._get_germline_start()
		self.germline_end = self._get_germline_end()
		self.sequence = self._get_sequence()
		self.reading_frame = self._get_reading_frame()
		self.gene_type = 'diversity'
		self.chain = 'heavy'
		self.nt_mutations = self._nt_mutations()

	def _get_top_germline(self):
		'''
		Returns the top scoring germline gene. If no germline gene scores
		higher than 9, then the top_germline attribute is set to 'None'.
		The minimum for reaching a score of 9 would be a 6nt alignment
		region with at least 5 matching nucleotides and a single mismatch.
		'''
		top_alignment = self.alignments[0]
		if top_alignment.alignment.score > 9:
			return top_alignment.target_id
		return None

	def _get_all_germlines(self):
		'Returns all germline genes'
		return [a.target_id for a in self.alignments]

	def _get_top_score(self):
		'Returns the score for the top scoring germline gene'
		top_alignment = self.alignments[0]
		return top_alignment.alignment.score

	def _get_all_scores(self):
		'Returns all germline gene scores'
		return [a.alignment.score for a in self.alignments]

	def _get_query_alignment(self):
		'''Returns the query alignment string for the
		top scoring germline gene alignment'''
		top_alignment = self.alignments[0]
		return top_alignment.aligned_query

	def _get_germline_alignment(self):
		'Returns the top scoring germline alignment'
		top_alignment = self.alignments[0]
		return top_alignment.aligned_target

	def _get_alignment_midline(self):
		'''Returns the alignment midline string for the
		top scoring germline gene alignment'''
		length = min(len(self.query_alignment), len(self.germline_alignment))
		query = self.query_alignment
		germ = self.germline_alignment
		midline = ['|' if query[i] == germ[i] else ' ' for i in range(length)]
		return ''.join(midline)

	def _get_alignment_length(self):
		'Returns the alignment length for the top scoring germline gene alignment'
		return len(self.germline_alignment)

	def _get_query_start(self):
		'''Returns the start position of the query alignment with
		the top germline gene'''
		top_alignment = self.alignments[0]
		return top_alignment.query_begin

	def _get_query_end(self):
		'''Returns the start position of the query alignment with
		the top germline gene'''
		top_alignment = self.alignments[0]
		return top_alignment.query_end

	def _get_germline_start(self):
		'Returns the start position of the top germline alignment'
		top_alignment = self.alignments[0]
		return top_alignment.target_begin

	def _get_germline_end(self):
		'Returns the end position of the top germline alignment'
		top_alignment = self.alignments[0]
		return top_alignment.target_end

	def _get_reading_frame(self):
		'''
		Identifies the diverstiy gene reading frame
		'''
		rf = (self.germline_start % 3) + 1
		return rf

	def _get_sequence(self):
		return self.query_alignment[self.query_start:self.query_end]

	def _nt_mutations(self):
		'''
		Identifies and annotates nucleotide mutations.
		'''
		from abstar.utils import mutations
		return mutations.nt_mutations(self)


@celery.task
def run(seq_file, output_dir, args):
	'''
	Wrapper function to multiprocess (or not) the assignment of V, D and J
	germline genes. Also writes the JSON-formatted output to file.

	Input is a a FASTA-formatted file of antibody sequences and the output directory.
	Optional input items include the species (supported species: 'human'); length of
	the unique antibody identifier (UAID); and debug mode (which forces single-threading
	and prints more verbose errors.)

	Output is the number of functional antibody sequences identified in the input file.
	'''
	try:
		output_filename = os.path.basename(seq_file)
		if args.output_type == 'json':
			output_file = os.path.join(output_dir, output_filename + '.json')
		elif args.output_type in ['imgt', 'hadoop']:
			output_file = os.path.join(output_dir, output_filename + '.txt')
		vdj_output = process_sequence_file(seq_file, args)
		if not vdj_output:
			return 0
		clean_vdjs = [vdj for vdj in vdj_output if vdj.rearrangement]
		output_count = write_output(clean_vdjs, output_file, args.output_type)
		return output_count
	except:
		raise Exception("".join(traceback.format_exception(*sys.exc_info())))
		# run.retry(exc=exc, countdown=5)


def write_output(output, outfile, output_type):
	from abstar.utils.output import build_output
	output_data = build_output(output, output_type)
	open(outfile, 'w').write('\n'.join(output_data))
	if output_type in ['json', 'hadoop']:
		return len(output_data)
	else:
		return len(output_data) - 1


def process_sequence_file(seq_file, args):
	'''
	Runs BLASTn to identify germline V, D, and J genes.

	Input is a Sequence object.

	Output is a list of VDJ objects.
	'''

	# Variable gene assignment
	vs = []
	seqs = [Sequence(s) for s in SeqIO.parse(open(seq_file, 'r'), 'fasta')]
	v_blast_records = blast(seq_file, args.species, 'V')
	for seq, vbr in zip(seqs, v_blast_records):
		try:
			v = assign_germline(seq, vbr, args.species, 'V')
			if v.strand == 'minus':
				seq.reverse_complement()
			logging.debug('ASSIGNED V-GENE: {}, {}'.format(seq.id, v.top_germline))
		except Exception, err:
			logging.debug('V-GENE ASSIGNMENT ERROR: {}'.format(seq.id))
			logging.debug('\n>{s}\n{q}\nexception = {e}'.format(
				s=seq.id, q=seq.sequence, e=traceback.format_exc().strip()))
			v = None
		finally:
			if v:
				v_end = len(v.query_alignment) + v.query_start
				if len(seq.region(start=v_end)) <= 10:
					v = None
			vs.append((seq, v))
	v_blast_results = [v[1] for v in vs if v[1]]
	seqs = [v[0] for v in vs if v[1]]
	failed_seqs = [v[0] for v in vs if not v[1]]
	logging.debug('V-ASSIGNMENT RESULT: for {}, {} of {} sequences failed v-gene assignment'.format(
		os.path.basename(seq_file), len(failed_seqs), len(seqs) + len(failed_seqs)))
	for fs in failed_seqs:
		pass
		# logging.debug('NO V-GENE ASSIGNMENT: {}'.format(seq.id))
	if not v_blast_results:
		seq_filename = os.path.basename(seq_file)
		logging.debug('NO VALID REARRANGEMENTS IN FILE: {}'.format(seq_filename))
		return None

	# Joining gene assignment
	js = []
	j_blastin = build_j_blast_input(seqs, v_blast_results)
	j_blast_records = blast(j_blastin.name, args.species, 'J')
	j_seqs = [Sequence(s) for s in SeqIO.parse(open(j_blastin.name, 'r'), 'fasta')]
	for i, jdata in enumerate(zip(j_seqs, j_blast_records)):
		j_seq, jbr = jdata
		try:
			j = assign_germline(j_seq, jbr, args.species, 'J')
			if not j:
				logging.debug('NO ASSIGNED J-GENE: {}'.format(j_seq.id))
			logging.debug('ASSIGNED J-GENE: {}, {}'.format(j_seq.id, j.top_germline))
		except:
			logging.debug('J-GENE ASSIGNMENT ERROR: {}'.format(j_seq.id))
			logging.debug(traceback.format_exc())
			try:
				vbr = v_blast_records[i]
				vseq = seqs[i]
				logging.debug('J-GENE ASSIGNMENT ERROR: {}\n{}\n{}'.format(j_seq.id,
																		   vseq.sequence,
																		   vbr.query_alignment))
			except:
				logging.debug('J-GENE ASSIGNMENT ERROR: {}, could not print query info'.format(j_seq.id))
				logging.debug(traceback.format_exc())
			j = None
		finally:
			js.append(j)
	os.unlink(j_blastin.name)

	# Build VDJ objects (including optional D gene assignment)
	vdjs = []
	for seq, v, j in zip(seqs, v_blast_results, js):
		try:
			if not v or not j:
				# vdjs.append(VDJ(seq, args, v, j))
				continue
			if v.chain == 'heavy':
				junc_start = len(v.query_alignment) + v.query_start
				junc_end = junc_start + j.query_start
				junction = seq.sequence[junc_start:junc_end]
				if junction:
					d = assign_d(seq.id, junction, args.species)
					logging.debug('ASSIGNED D-GENE: {}, {}'.format(seq.id, d.top_germline))
					vdjs.append(VDJ(seq, args, v, j, d))
					continue
				vdjs.append(VDJ(seq, args, v, j))
			else:
				vdjs.append(VDJ(seq, args, v, j))
			logging.debug('VDJ SUCCESS: {}'.format(seq.id))
		except:
			logging.debug('VDJ ERROR: {}'.format(seq.id))
	return vdjs


def build_j_blast_input(seqs, v_blast_results):
	j_fastas = []
	for seq, vbr in zip(seqs, v_blast_results):
		start = len(vbr.query_alignment) + vbr.query_start + vbr.fs_indel_adjustment + vbr.nfs_indel_adjustment
		j_fastas.append(seq.as_fasta(start=start))
	j_blastin = tempfile.NamedTemporaryFile(delete=False)
	j_blastin.write('\n'.join(j_fastas))
	j_blastin.close()
	return j_blastin


def blast(seq_file, species, segment):
	'''
	Runs BLASTn against an antibody germline database.

	Input is a FASTA file of sequences (the file path, not a handle), the species of origin
	of the sequences to be queried, and the gene segment (options are: 'V', 'D', or 'J')
	'''
	mod_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	blast_path = os.path.join(mod_dir, 'blast/blastn_{}'.format(platform.system().lower()))
	blast_db_path = os.path.join(mod_dir, 'blast/dbs/{}_gl_{}'.format(species.lower(), segment.upper()))
	blastout = tempfile.NamedTemporaryFile(delete=False)
	blastn_cmd = NcbiblastnCommandline(cmd=blast_path,
									   db=blast_db_path,
									   # cmd='{}/blast/blastn_{}'.format(os.getcwd(), platform.system().lower()),
									   # db='{}/blast/dbs/{}_gl_{}'.format(os.getcwd(), species.lower(), segment.upper()),
									   query=seq_file,
									   out=blastout.name,
									   outfmt=5,
									   dust='no',
									   word_size=_word_size(segment),
									   max_target_seqs=10,
									   evalue=_evalue(segment),
									   reward=_match_reward(segment),
									   penalty=_mismatch_penalty(segment),
									   gapopen=_gap_open(segment),
									   gapextend=_gap_extend(segment))
	stdout, stderr = blastn_cmd()
	blast_records = [br for br in NCBIXML.parse(blastout)]
	os.unlink(blastout.name)
	return blast_records


def _word_size(segment):
	'Returns BLASTn word size for the given gene segment'
	word_sizes = {'V': 11,
				  'D': 4,
				  'J': 7}
	return word_sizes[segment]


def _gap_open(segment):
	'Returns BLASTn gap-open penalty for the given gene segment'
	gap_open = {'V': 5,
				'D': 4,
				'J': 5}
	return gap_open[segment]


def _gap_extend(segment):
	'Returns BLASTn gap-extend penalty for the given gene segment'
	gap_extend = {'V': 2,
				  'D': 2,
				  'J': 2}
	return gap_extend[segment]


def _match_reward(segment):
	'Returns BLASTn match reward for the given gene segment'
	match = {'V': 1,
			 'D': 1,
			 'J': 1}
	return match[segment]


def _mismatch_penalty(segment):
	'Returns BLASTn mismatch penalty for the given gene segment'
	mismatch = {'V': -1,
				'D': -1,
				'J': -1}
	return mismatch[segment]


def _evalue(segment):
	'Returns minimum BLASTn e-value for the given gene segment'
	evalue = {'V': 1,
			  'D': 100000,
			  'J': 1000}
	return evalue[segment]


def assign_germline(seq, blast_record, species, segment):
	'''
	Identifies germline genes for a given antibody sequence (seq).

	Input is a Sequence object, the species of origin, the gene
	segment to be assigned (options are 'V' or 'J') and, optionally, the
	starting and ending points of the possible germline gene location.

	Output is a BlastResult object.
	'''
	blast_result = BlastResult(seq.id, blast_record, seq.region(), species)
	if blast_result.gene_type == 'variable':
		blast_result.realign_variable(blast_result.top_germline)
	# if blast_result.gene_type == 'joining':
	# 	blast_result.realign_joining(blast_result.top_germline)
	blast_result.annotate()
	return blast_result


def assign_d(seq_id, seq, species):
	'''
	Identifies the germline diversity gene for a given sequence.
	Alignment is performed using the ssw_wrap.Aligner.align function.

	Input is a junction sequence (as a string) and the species of origin.

	Output is a DiversityResult object.
	'''
	mod_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	db_file = os.path.join(mod_dir, 'ssw/dbs/{}_D.fasta'.format(species.lower()))
	db_handle = open(db_file, 'r')
	seqs = [s for s in SeqIO.parse(db_handle, 'fasta')]
	rc_seqs = [Sequence(s).rc() for s in seqs]
	seqs.extend(rc_seqs)
	db_handle.close()
	ssw = Aligner(seq,
				  match=3,
				  mismatch=2,
				  gap_open=20,
				  gap_extend=2,
				  report_cigar=True)
	alignments = []
	for s in seqs:
		alignments.append(Alignment(s.id,
									seq,
									str(s.seq),
									ssw.align(str(s.seq),
											  min_score=0,
											  min_len=0)))
	alignments.sort(key=lambda x: x.alignment.score,
					reverse=True)
	return DiversityResult(seq_id, seq, alignments[:5])
