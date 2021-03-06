"""Utilities for parsing who_did_what text files."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import os
from string import punctuation
import re
import numpy as np
import tensorflow as tf
from tensorflow.contrib import learn
from sklearn.preprocessing import LabelEncoder


def get_vocab(questions, context, min_frequency=10):
    vocab_data = []
    vocab_data.extend(questions)
    vocab_data.extend(context)

    max_length = max([len(row.split(" ")) for row in vocab_data])
    vocab_processor = learn.preprocessing.VocabularyProcessor(
        max_length, min_frequency=min_frequency)
    vocab_processor.fit(vocab_data)
    print("done fitting vocab!")
    return vocab_processor


def mask_narrow(mat):
    mask = np.all(mat == 0, axis=0)
    return mat[:, ~mask]


def vocab_transform(mat, vocab):
    return mask_narrow(np.array(list(vocab.transform(mat))))


def clean_str(string, choice=False):
    """
    Tokenization/string cleaning for all datasets except for SST.
    Original taken from https://github.com/yoonkim/CNN_sentence/blob/master/process_data.py
    """
    string = re.sub(r"[^A-Za-z0-9(),!?\'\`]", " ", string)
    string = re.sub(r"\'s", " \'s", string)
    string = re.sub(r"\'ve", " \'ve", string)
    string = re.sub(r"n\'t", " n\'t", string)
    string = re.sub(r"\'re", " \'re", string)
    string = re.sub(r"\'d", " \'d", string)
    string = re.sub(r"\'ll", " \'ll", string)
    string = re.sub(r",", " , ", string)
    string = re.sub(r"!", " ! ", string)
    string = re.sub(r"\(", " \( ", string)
    string = re.sub(r"\)", " \) ", string)
    string = re.sub(r"\?", " \? ", string)
    string = re.sub(r"\s{2,}", " ", string)
    string = re.sub(r"`", "'", string)
    string = string.replace("\\)", "rrb")
    string = string.replace("\\(", "lrb")
    string = string.replace("''", " ")
    string = string.replace("' ", " ")
    return string.strip().lower()


def _read_words(filename):
    with tf.gfile.GFile(filename, "r") as f:
        fi = f.read().decode("utf-8").strip().split("\n")
    return [re.split('[$$$\s]', x) for x in fi]


def build_choices(choices):
    all_choices = [item for sublist in choices for item in sublist]
    le = LabelEncoder()
    le.fit(all_choices)
    choice_to_id = dict(zip(le.classes_, range(len(le.classes_))))
    return choice_to_id


def strip_punctuation(lines, return_len=False):
    """
    Strip punctuation from a list of lines and optionally return the lengths.
    """
    stripped_lines = []
    if return_len:
        lengths = []

    for line in lines:
        tokens = [token for token in clean_str(line).split(' ') if token not in punctuation]
        stripped_lines.append(' '.join(tokens))
        if return_len:
            lengths.append(len(tokens))
    if return_len:
        return stripped_lines, np.array(lengths)
    return stripped_lines


def encode_choices(context, question, choices, label, i):
    """
    Assign numbers to entities based on occurence in document;
    encode that choice in the document
    """
    entity_num = 0
    choices_map = {}
    new_context = context.split(" ")
    new_question = question.split(" ")
    word_ent_map = {}
    new_word = None
    new_label = None

    for choice in choices:
        if choice not in choices_map:
            choices_map[choice] = "@entity%s" % entity_num
            entity_num += 1
        if choice not in context:
            print("choice does not exist in context: %s, id %d" % (choice, i))
        context = context.replace(choice, choices_map[choice])
        question = question.replace(choice, choices_map[choice])
        label = label.replace(choice, choices_map[choice])
    new_choices = [choices_map[x] for x in choices]
    return context, question, new_choices,label,choices_map


def load_data(data_path=None):
    """
    Return a tuple of a

    1. List of contexts.
    2. List of questions.
    3. List of choices.
    4. List of labels.
    """
    qu_fn = 'qu.txt'
    context_fn = 'context.txt'
    choice_fn = 'choices.txt'
    labels_fn = 'labels.txt'
    if data_path is None:
        data_path = os.getcwd()
    qu_p = os.path.join(data_path, qu_fn)
    cont_p = os.path.join(data_path, context_fn)
    ch_p = os.path.join(data_path, choice_fn)
    lab_p = os.path.join(data_path, labels_fn)

    questions_file = open(qu_p, "r")
    questions = strip_punctuation(questions_file.readlines())
    questions_file.close()

    context_file = open(cont_p, "r")
    context = strip_punctuation(context_file.readlines())
    context_file.close()

    choices_file = open(ch_p, "r")
    choices = choices_file.read().strip().split("\n")
    choices = [x.strip().split("$$$") for x in choices]
    for i, lines in enumerate(choices):
        choices[i] = strip_punctuation(lines)
    choices_file.close()

    # Remove duplicate choices and replace the longest string
    # first.
    new_choices = []
    choices_map_all = []
    for i, choice in enumerate(choices):
        dup_choices = list(set(choice))
        longest_first = sorted(dup_choices, key=lambda x: -len(x))
        new_choices.append(longest_first)

    data_size = len(context)
    labels = strip_punctuation(open(lab_p).readlines())

    for i in range(data_size):
        context[i], questions[i], new_choices[i], labels[i], choices_map = \
                encode_choices(
                    context[i],
                    questions[i],
                    new_choices[i],
                    labels[i], i)
        choices_map_all.append(choices_map)
    context_lens = np.array([len(c.split(" ")) for c in context])
    qs_lens = np.array([len(q.split(" ")) for q in questions])

    return (
        context, questions, new_choices, labels, choices_map_all,
        context_lens, qs_lens)


def get_seq_length(lengths, step_ind, num_steps):
    """
    Get truncated sequence length.
    """
    var_qs_len = step_ind * num_steps * np.ones_like(lengths)
    return np.maximum(0, np.minimum(num_steps, lengths - var_qs_len)).astype(np.int32)

def pad_eval(mat, length):
    """
    Pad eval matrix to size of training matrix
    """
    s = mat.shape
    if length < s[1]:
        print("Training width %s is less than provided width (%s). Cutting off"
              %(length, s[1]))
        mat = mat[:, :length]
    else:
        pad = np.zeros((s[0], length - s[1]))
        mat = np.concatenate((mat, pad),axis=1)
    return mat

def batch_iter(contexts, questions, choices, labels, choices_map,
               context_lens, qs_lens, batch_size=32,
               random_state=None, context_num_steps=None,
               question_num_steps=None):
    """
    Generates a batch iterator for a dataset.
    """
    rng = np.random.RandomState(random_state)

    choices = np.array([" ".join(x) for x in choices])
    labels = np.array(labels)
    choices_map = np.array(choices_map)

    data_size = len(contexts)
    data_indices = np.arange(data_size)
    # sort by context lengths
    sorted_context_inds = np.argsort(context_lens)
    num_batches_per_epoch = int(data_size / batch_size)

    # cont_len = contexts.shape[1]
    # cont_lim = (cont_len // context_num_steps) * context_num_steps
    # qs_len = questions.shape[1]
    # qs_lim = (qs_len // question_num_steps) * question_num_steps
    #
    # # Clip contexts
    # contexts = contexts[:, :min(cont_len, context_num_steps)]
    #
    # # Clip questions
    # questions = questions[:, :min(qs_len, question_num_steps)]

    """
    # Shuffle the data at each epoch
    shuffle_indices = rng.permutation(data_indices)
    shuffled_qs = questions[shuffle_indices]
    shuffled_cont = contexts[shuffle_indices]
    shuffled_choices = choices[shuffle_indices]
    shuffled_map = choices_map[shuffle_indices]
    shuffled_labels = labels[shuffle_indices]
    shuf_cont_lens = context_lens[shuffle_indices]
    shuf_qs_lens = qs_lens[shuffle_indices]
    """

    shuffle_indices = sorted_context_inds
    shuffled_qs = questions[shuffle_indices]
    shuffled_cont = contexts[shuffle_indices]
    shuffled_choices = choices[shuffle_indices]
    shuffled_map = choices_map[shuffle_indices]
    shuffled_labels = labels[shuffle_indices]
    shuf_cont_lens = context_lens[shuffle_indices]
    shuf_qs_lens = qs_lens[shuffle_indices]

    for batch_num in range(num_batches_per_epoch):
        start_index = batch_num * batch_size
        end_index = start_index + batch_size

        yield (
            mask_narrow(shuffled_qs[start_index: end_index]),
            mask_narrow(shuffled_cont[start_index: end_index]),
            shuffled_choices[start_index: end_index],
            shuffled_labels[start_index: end_index],
            shuffled_map[start_index: end_index],
            shuf_cont_lens[start_index: end_index],
            shuf_qs_lens[start_index: end_index])

# Usage:
# 1. Encode questions and context with identities.
# contexts, questions, new_choices, labels, choices_map_all, context_lens, qs_lens =
#    load_data(data_path="")
# 2. Fit vocabulary with questions and context.
# vocab = get_vocab(contexts, questions)
# 3. Transform context and questions
# contexts = vocab_transform(contexts, vocab)
# questions = vocab_transform(questions, vocab)
# 4. Give to batch_iter
# batch_iter(contexts, questions, choices, labels, choices_map,
#            context_lens, qs_lens,
