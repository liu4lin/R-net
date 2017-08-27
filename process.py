# -*- coding: utf-8 -*-
#/usr/bin/python2

import codecs
import numpy as np
import json
import unicodedata
import re
import nltk
import sys
import argparse

from tqdm import tqdm
from nltk.tokenize import *
from params import Params

reload(sys)
sys.setdefaultencoding('utf8')

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

parser = argparse.ArgumentParser()
parser.add_argument('-p','--process', default = False, type = str2bool, help='Use the coreNLP tokenizer.', required=False)
args = parser.parse_args()

if args.process:
    from stanford_corenlp_pywrapper import CoreNLP
    proc = CoreNLP("ssplit",corenlp_jars=[Params.coreNLP_dir + "/*"])

def tokenize_corenlp(text):
    parsed = proc.parse_doc(text)
    tokens = []
    for sent in parsed['sentences']:
        tokens.extend(sent['tokens'])
    return tokens

class data_loader(object):
    def __init__(self,pretrained = None):
        self.c_dict = {"_UNK":0}
        self.w_dict = {"_UNK":0}
        self.w_occurence = 0
        self.c_occurence = 0
        self.w_count = 1
        self.c_count = 1
        self.w_unknown_count = 0
        self.c_unknown_count = 0
        self.append_dict = True
        self.invalid_q = 0

        if pretrained:
            self.append_dict = False
            self.process_vocab(pretrained)
            self.ids2word = {v: k for k, v in self.w_dict.iteritems()}

    def ind2word(self,ids):
        output = []
        for i in ids:
            output.append(str(self.ids2word[i]))
        return " ".join(output)

    def ind2char(self,ids):
        output = []
        for i in ids:
            for j in i:
                output.append(str(self.ids2char[j]))
            output.append(" ")
        return "".join(output)

    def process_vocab(self,wordvecs):
        with codecs.open(wordvecs,"rb","utf-8") as f:
            line = f.readline()
            i = 0
            while line:
                vocab = line.split(" ")
                if len(vocab) != 301:
                    line = f.readline()
                    continue
                vocab = normalize_text(''.join(vocab[0:-300]).decode("utf-8"))
                self.process_char(vocab)
                if vocab in self.w_dict:
                    self.w_count += 1
                if vocab not in self.w_dict:
                    self.w_dict[vocab] = self.w_count
                    self.w_count += 1
                line = f.readline()
                i += 1
                if i % 100 == 0:
                    sys.stdout.write("\rProcessing line %d"%i)
            print("\n")

    def process_json(self,dir):
        self.data = json.load(codecs.open(dir,"rb","utf-8"))
        self.loop(self.data)
        self.ids2char = {v: k for k, v in self.c_dict.iteritems()}
        with codecs.open("dictionary.txt","wb","utf-8") as f:
            for key, value in sorted(self.w_dict.iteritems(), key=lambda (k,v): (v,k)):
                f.write("%s: %s" % (key, value) + "\n")

    def loop(self,data):
        watch_list = ["one"]
        for topic in data['data']:
            for para in topic['paragraphs']:
                for qas in para['qas']:
                    for ans in qas['answers']:
                        if ans['text'] in watch_list:
                            continue
                        elif len(ans['text']) <= 2:
                            continue
                        cond = {ans['text']:" " + ans['text'] + " "}
                        cond = dict((re.escape(k), v) for k, v in cond.iteritems())
                        pattern = re.compile("|".join(cond.keys()))
                        para['context'] = pattern.sub(lambda m: cond[re.escape(m.group(0))], para['context'])

                words_c,chars_c = self.add_to_dict(para['context'])
                if len(words_c) > Params.max_len:
                    continue

                for qas in para['qas']:
                    question = qas['question']
                    words,chars = self.add_to_dict(question)
                    write_file(words,"words_questions.txt","\n")
                    write_file(chars,"chars_questions.txt","\n")
                    write_file(words_c,"words_context.txt")
                    write_file(chars_c,"chars_context.txt")
                    for ans in qas['answers']:
                        ans_ids,_ = self.add_to_dict(ans['text'])
                        (start_i, finish_i) = find_answer_index(words_c, ans_ids)
                        if start_i == -1:
                            self.invalid_q += 1
                        write_file([str(start_i),str(finish_i)],"indices.txt","\n")

    def process_word(self,line):
        for word in splitted_line:
            word = word.replace(" ","").strip()
            word = normalize_text(''.join(word).decode("utf-8"))
            if word:
                if not word in self.w_dict:
                    self.w_dict[word] = self.w_count
                    self.w_count += 1

    def process_char(self,line):
        for char in re.sub(r"[^a-zA-Z0-9'()_;:\[\]\-\"\)\(.,?]", "", line.strip()):
            if char:
                if char != " ":
                    if not char in self.c_dict:
                        self.c_dict[char] = self.c_count
                        self.c_count += 1

    def add_to_dict(self, line):
        splitted_line = re.split(r'[`\--=~!@#$%^&*\"“”()_+ \[\]{};\\:"|<,./<>?]', line.strip())
        splitted_line = [sl for sl in splitted_line if sl]
        splitted_line = " ".join(splitted_line)
        splitted_line = tokenize_corenlp(splitted_line)
        if self.append_dict:
            self.process_word(splitted_line)

        self.process_char(splitted_line)
        words = []
        chars = []
        for i,word in enumerate(splitted_line):
            word = word.replace(" ","").strip()
            word = normalize_text(''.join(word).decode("utf-8"))
            if word:
                if i > 0:
                    chars.append("_SPC")
                for char in word:
                    char = self.c_dict.get(char,self.c_dict["_UNK"])
                    chars.append(str(char))
                    self.c_occurence += 1
                    if char == 0:
                        self.c_unknown_count += 1

                word = self.w_dict.get(word.strip().strip(" "),self.w_dict["_UNK"])
                words.append(str(word))
                self.w_occurence += 1
                if word == 0:
                    self.w_unknown_count += 1
        return (words, chars)

def load_glove(dir_):
    glove = np.zeros((Params.vocab_size,300),dtype = np.float32)
    with codecs.open(dir_,"rb","utf-8") as f:
        line = f.readline()
        i = 1
        while line:
            if i % 100 == 0:
                sys.stdout.write("\rProcessing %d vocabs"%i)
            vector = line.split(" ")
            if len(vector) != 301:
                line = f.readline()
                continue
            vector = vector[-300:]
            if vector:
                try:
                    vector = [float(n) for n in vector]
                except:
                    assert 0
                vector = np.asarray(vector, np.float32)
                try:
                    glove[i] = vector
                except:
                    assert 0
            line = f.readline()
            i += 1
    print("\n")
    glove_map = np.memmap(Params.data_dir + "glove.np", dtype='float32', mode='write', shape=(Params.vocab_size,300))
    glove_map[:] = glove

def find_answer_index(context, answer):
    window_len = len(answer)
    if window_len == 1:
        if answer[0] in context:
            return (context.index(answer[0]), context.index(answer[0]))
        else:
            return(-1,-1)
    for i in range(len(context)):
        if context[i:i+window_len] == answer:
            return (i, i + window_len)
    return(-1,-1)

def normalize_text(text):
    return unicodedata.normalize('NFD', text)

def print_keys(dict):
    for key, value in sorted(dict.iteritems(), key=lambda (k,v): (v,k)):
        print("%s: %s" % (key, value) + "\n")

def tok2id(tokens,dict_):
    return [str(dict_.get(tok,dict_["_UNK"])) for tok in tokens]

def to_text_file(line, dir):
    with codecs.open(dir,"ab","utf-8") as f:
        f.write(line + "\n")

def write_file(indices, dir, separate = "\n"):
    with codecs.open(Params.data_dir + dir,"ab","utf-8") as f:
        f.write(" ".join(indices) + separate)

def pad_data(data, max_word):
    padded_data = np.zeros((len(data),max_word),dtype = np.int32)
    for i,line in enumerate(data):
        for j,word in enumerate(line):
            padded_data[i,j] = word
    return padded_data

def pad_char_data(data, max_char, max_words):
    padded_data = np.zeros((len(data),max_words,max_char),dtype = np.int32)
    for i,line in enumerate(data):
        for j,word in enumerate(line):
            for k,char in enumerate(word):
                padded_data[i,j,k] = char
    return padded_data

def load_target(dir):
    data = []
    count = 0
    with codecs.open(dir,"rb","utf-8") as f:
        line = f.readline()
        while count < 1000 if Params.debug else line:
        # while count < 1000:
            line = [int(w) for w in line.split()]
            data.append(line)
            count += 1
            line = f.readline()
    return data

def load_word(dir):
    data = []
    w_len = []
    count = 0
    with codecs.open(dir,"rb","utf-8") as f:
        line = f.readline()
        while count < 1000 if Params.debug else line:
        # while count < 1000:
            line = [int(w) for w in line.split()]
            data.append(line)
            count += 1
            w_len.append(len(line))
            line = f.readline()
    return data, w_len

def load_char(dir):
    data = []
    w_len = []
    c_len_ = []
    count = 0
    with codecs.open(dir,"rb","utf-8") as f:
        line = f.readline()
        while count < 1000 if Params.debug else line:
        # while count < 1000:
            c_len = []
            chars = []
            line = line.split("_SPC")
            for word in line:
                c = [int(w) for w in word.split()]
                c_len.append(len(c))
                chars.append(c)
            data.append(chars)
            line = f.readline()
            count += 1
            c_len_.append(c_len)
            w_len.append(len(c_len))
    return data, c_len_, w_len

def max_value(inputlist):
    max_val = 0
    for list_ in inputlist:
        for val in list_:
            if val > max_val:
                max_val = val
    return max_val

def main():
    loader = data_loader(pretrained = Params.glove_dir)
    loader.process_json(Params.data_dir + "train-v1.1.json")
    load_glove(Params.glove_dir)

if __name__ == "__main__":
    main()