#!/usr/bin/python
# -*- coding: utf-8 -*

import math
import os
import sys
import time
import unicodecsv

import click
import requests

def trace(str):
	print str.encode('utf-8')

def relative_path(filename):
	return os.path.join(os.path.dirname(__file__), filename)

class CSVDict(object):
	def __init__(self,filename,keys,delimiter=','):
		self.filename = filename
		self.keys = keys
		self.delimiter = delimiter
		self.entries = []
		self.load()

	def load(self):
		self.entries = []
		with open(self.filename, "rb") as file:
			reader = unicodecsv.reader(file,delimiter=self.delimiter)
		        count = 0
		        for row in reader:
		        	self.entries.append(row)
		return self.entries

	def entry(self,i):
		try:
			entry = self.entries[i]
			res = { self.keys[i]:entry[i] for i in range(0,len(entry)) }
			if res.get('definition'):
				res['definition'] = res['definition'].split('/')
			return res
		except:
			return False

class CharsDict(CSVDict):
	def __init__(self):
		super(CharsDict, self).__init__(
			filename=relative_path('characters.csv'),
			keys=['index','character','raw_frequency','frequency','pinyin','definition'],
			delimiter='	'
		)

	def weight(self,i):
		if i == 0:
			return float(self.entry(0)['frequency'])
		else:
			return float(self.entry(i)['frequency']) - float(self.entry(i-1)['frequency'])

	def lookup(self,char):
		if type(char) == int or type(char) == float:
			char = int(char)
			res = self.entry(char)
			res['weight'] = self.weight(char)
			return res
		else:
			for i, e in enumerate(self.entries):
				if e[1] == char:
					res = self.entry(i)
					res['weight'] = self.weight(i)
					return res
		return False

class CEDICT(CSVDict):
	def __init__(self):
		super(CEDICT,self).__init__(
			filename=relative_path('cedict.csv'),
			keys=['characters-traditional','characters','pinyin','definition'],
			delimiter='$'
		)

	def lookup(self,chars):
		if type(chars) == int or type(chars) == float:
			return self.entry(int(chars))
		else:
			for i, e in enumerate(self.entries):
				if e[0] == chars or e[1] == chars:
					return self.entry(i)
		return False



class BigramsDict(CSVDict):
	def __init__(self):
		super(BigramsDict,self).__init__(
			filename=relative_path('bigrams.csv'),
			keys=['index','characters','frequency','mutual_information','serial_number'],
			delimiter='	'
		)

	def lookup(self,chars):
		if type(chars) == int or type(chars) == float:
			return self.entry(int(chars))
		else:
			for i, e in enumerate(self.entries):
				if e[1] == chars:
					return self.entry(i)
		return False

class KnowledgeBase(object):
	def __init__(self,known_characters=1000):
		self.known_characters= known_characters
		self.characters = CharsDict()
		self.cedict = CEDICT()
		self.bigrams = BigramsDict()

	def get_char(self,i):
		char = self.characters.entry(i)['character']
		print char.encode('utf-8')
		return char

	def get_bigram(self,i):
		chars = self.bigrams.entry(i)['characters']
		print chars.encode('utf-8')
		return chars

	def prob_char_known(self,char):
		# Wait, is it a Latin character?
		if char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789':
			return 1
		# Weighted random sample
		# Pull (known) from (total) without replacement
		# What are the odds that (char) is in sample?
		# Sum n=1..known: P(char in pull n)
		lookup = self.characters.lookup(char)
		if not lookup:
			return 0
		total = len(self.characters.entries)
		known = self.known_characters
		scale = 0.82
		weight = (lookup['weight'] / 100) ** scale
		p_not_pulled = 1
		p = 0
		for i in range(0,known):
			p_this_pull = p_not_pulled * weight
			p += p_this_pull
			p_not_pulled = 1 - p
			weight = weight * total / (total - 1)
		return p

	def prob_bigram_known(self,bigram):
		if(type(bigram) == int or type(bigram) == float):
			bigram = self.get_bigram(int(bigram))
		if type(bigram) == dict:
			chars = bigram['characters']
		else:
			chars = bigram
			bigram = self.bigrams.lookup(chars)
			if not bigram:
				return False
		p = 1
		for c in chars:
			p *= self.prob_char_known(c)
		return p * math.log10(float(bigram['mutual_information']))

	def prob_word_known(self,word):
		if len(word) == 1:
			return self.prob_char_known(word)
		if len(word) == 2 and self.bigrams.lookup(word):
			return self.prob_bigram_known(word)
		else:
			p = 1
			for c in word:
				p *= self.prob_char_known(c)
			return p

	def do_know_char(self,char):
		threshold = 0.5
		return self.prob_char_known(char) >= threshold

	def char_2k_dist(self):
		known = ''
		unknown = ''
		for i in range(0,2000):
			char = self.characters.lookup(i)['character']
			if self.do_know_char(char):
				known += char
			else:
				unknown += char
		print 'K:', len(known)
		print 'U:', len(unknown)

	def prob_char_demo(self):
		test = [100,250,500,750,1000,1250,1500,1750,2000]
		for t in test:
			self.known_characters = t
			print 'Number known:', self.known_characters
			self.char_2k_dist()

class Shentan(object):
	def __init__(self,known_characters=None,quiet=False):
		self.quiet = quiet
		self.knowledge = KnowledgeBase(known_characters)

	def analyze_from_source(self,source):
		if source.startswith('http://') or source.startswith('https://'):
			text = requests.get(source).text
		else:
			with open(source, "rb") as file:
				text = unicode(file.read(),'utf-8')
		return self.analyze(text)

	def analyze(self,text):
		pointer = 0
		words = []
		if not self.quiet:
			print ''
		while pointer < len(text):
			# Do the thing
			char = text[pointer]
			is_readable = u'\u4e00' <= char <= u'\u9fff'
			# is_readable = is_readable or char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
			if not is_readable:
				pointer += 1
				continue
			lookup = char
			forward = 1
			while True:
				check = self.knowledge.cedict.lookup(text[pointer:pointer+forward])
				if check:
					lookup = text[pointer:pointer+forward]
					forward += 1
				else: 
					break
			words.append(lookup)
			pointer += len(lookup)
			# Talk about the thing
			if not self.quiet:
				sys.stdout.write("\033[F")
				print 'Shentan is doing its thing... ' + '(' + str(pointer) + '/' + str(len(text)) + ')'
		# We finished the thing!
		if not self.quiet:
			sys.stdout.write("\033[F")
			print 'Shentan is doing its thing... ' + '(' + str(len(text)) + '/' + str(len(text)) + ')'
		# Print the results
		words = filter(lambda word: self.knowledge.prob_word_known(word) < 0.5,words)
		def f7(seq):
		    seen = set()
		    seen_add = seen.add
		    return [ x for x in seq if not (x in seen or seen_add(x))]
		words = f7(words)
		if not self.quiet:
			print ''
			if len(words) > 0:
				print 'Here are ' + str(len(words)) + ' words you might need to know:'
			else:
				print u'很抱歉!'
				print 'Shentan couldn\'t find any words you might be unfamiliar with. Try inputting a smaller number of known characters.'
			print ''
		for word in words:
			lookup = self.knowledge.cedict.lookup(word)
			if lookup:
				print lookup['characters'].encode('utf-8') + ' ' + lookup['pinyin'].encode('utf-8') + ':'
				for definition in lookup['definition']:
					print '\t' + definition.encode('utf-8')
				print ''


@click.command()
@click.option('-q', default=False,is_flag=True,help='Quiet mode: don\'t show progress indicator')
@click.argument('known-characters', default=1000)
@click.argument('text-source',required=False)
def main(known_characters,q,text_source=None):
	s = Shentan(known_characters,q)
	s.analyze_from_source(text_source)

if __name__ == '__main__':
	main()

