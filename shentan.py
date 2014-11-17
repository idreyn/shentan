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
	def __init__(self,filename,keys,delimiter=',',key_index=0):
		self.filename = filename
		self.keys = keys
		self.key_index = key_index
		self.delimiter = delimiter
		self.entries = {}
		self.length = 0
		for item, last in self.load():
			yield item, last

	def load(self):
		self.entries = {}
		with open(self.filename, "rb") as file:
			reader = unicodecsv.reader(file,delimiter=self.delimiter)
		        count = 0
		        last = None
		        for row in reader:
		        	if not self.entries.get(row[self.key_index]):
			        	self.length += 1
			        	self.entries[row[self.key_index]] = row
			        	yield row[self.key_index], last
			        	last = row[self.key_index]

	def entry(self,i):
		try:
			entry = self.entries[i]
			res = { self.keys[i]:entry[i] for i in range(0,min(len(entry),len(self.keys))) }
			if res.get('definition'):
				res['definition'] = res['definition'].split('/')
			return res
		except:
			return False

class CharsDict(CSVDict):
	def __init__(self):
		index = 1
		for this, prev in super(CharsDict, self).__init__(
			filename=relative_path('characters.csv'),
			keys=['index','character','raw_frequency','frequency','pinyin','definition','weight','index'],
			delimiter='	',
			key_index=1
		):
			# 3 is the index of 'frequency' in the keys array
			if prev:
				self.entries[this] += [float(self.entries[this][3]) - float(self.entries[prev][3])]
			else:
				self.entries[this] += [float(self.entries[this][3])]
			self.entries[this] += [index]
			index += 1

	def lookup(self,char):
		try:
			res = self.entry(char)
			return res
		except:
			return False

class CEDICT(CSVDict):
	def __init__(self,key_index=1):
		list(super(CEDICT,self).__init__(
			filename=relative_path('cedict.csv'),
			keys=['characters-traditional','characters','pinyin','definition'],
			delimiter='$',
			key_index=key_index
		))

	def lookup(self,chars):
		return self.entry(chars)

class TraditionalCEDICT(CEDICT):
	def __init__(self):
		super(TraditionalCEDICT,self).__init__(
			key_index=0
		)

class BigramsDict(CSVDict):
	def __init__(self):
		list(super(BigramsDict,self).__init__(
			filename=relative_path('bigrams.csv'),
			keys=['index','characters','frequency','mutual_information','serial_number'],
			delimiter='	',
			key_index=1
		))

	def lookup(self,chars):
		return self.entry(chars)

class KnowledgeBase(object):
	def __init__(self,known_characters=1000):
		self.known_characters= known_characters
		self.characters = CharsDict()
		self.cedict = CEDICT()
		self.trad_cedict = TraditionalCEDICT()
		self.bigrams = BigramsDict()

	def get_char(self,i):
		char = self.characters.entry(i)['character']
		return char

	def get_bigram(self,i):
		chars = self.bigrams.entry(i)['characters']
		return chars

	def prob_char_known(self,char):
		# Wait, is it a Latin character?
		if char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789':
			return 1

		lookup = self.characters.lookup(char)
		if not lookup:
			return 0
		known = self.known_characters
		index = lookup['index']
		# This is a magic number that denotes the probability that if you
		# know n characters, you also know the nth character in the frequency list.
		# Season to taste.
		prob_head_char_known = 0.5
		return min(1,prob_head_char_known * (known / index))

	def prob_bigram_known(self,bigram):
		if(type(bigram) == int or type(bigram) == float):
			bigram = self.get_bigram(int(bigram))
		if type(bigram) == dict:
			chars = bigram['characters']
		else:
			chars = bigram
			bigram = self.bigrams.lookup(chars)
			if not bigram:
				return 0
		p = 1
		for c in chars:
			p *= self.prob_char_known(c)
		return p * math.log10(float(bigram['mutual_information']))

	def prob_word_known(self,word):
		if len(word) == 1:
			p = self.prob_char_known(word)
		if len(word) == 2:
			p = self.prob_bigram_known(word)
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

	def jianti_to_fanti(self,chars):
		res = ''
		for c in chars:
			if entry:
				res += self.knowledge.cedict.entry(c)['characters-traditional']
			else:
				res += c
		return res

	def fanti_to_jianti(self,chars):
		res = ''
		for c in chars:
			entry = self.knowledge.trad_cedict.entry(c)
			if entry:
				res += self.knowledge.trad_cedict.entry(c)['characters']
			else:
				res += c
		return res		

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
			while pointer + forward < len(text):
				check = self.knowledge.cedict.lookup(text[pointer:pointer+forward])
				check_trad = self.knowledge.trad_cedict.lookup(text[pointer:pointer+forward])
				if check:
					lookup = text[pointer:pointer+forward]
					forward += 1
				elif check_trad:
					lookup = text[pointer:pointer+forward]
					forward += 1
				else:
					break
			if self.knowledge.prob_word_known(lookup) < 0.5 and not lookup in words:
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
			if not lookup:
				lookup = self.knowledge.trad_cedict.lookup(word)
			if lookup:
				print word.encode('utf-8') + ' ' + lookup['pinyin'].encode('utf-8') + ':'
				for definition in lookup['definition']:
					print '\t' + definition.encode('utf-8')
				print ''
			else:
				print word
				print '\t' + 'No definition found.'
				print ' '


@click.command()
@click.option('-q', default=False,is_flag=True,help='Quiet mode: don\'t show progress indicator')
@click.argument('known-characters', default=1000)
@click.argument('text-source',required=False)
def main(known_characters,q,text_source=None):
	try:
		s = Shentan(known_characters,q)
		s.analyze_from_source(text_source)
	except Exception as e:
		print e
		print "That didn't work. Run Shentan with the --help flag for usage help."

if __name__ == '__main__':
	main()

