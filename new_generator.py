# -*- coding:utf-8 -*-

from word_vec2 import word2Vec
from word_dict import wordDict, end_of_sentence, start_of_sentence
from data_utils import batch_train_data
from paths import save_dir
from pron_dict import PronDict
from random import random
from singleton import Singleton
from utils import WORD_VEC_DIM, NUM_OF_SENTENCES
import numpy as np
import os
import sys
import tensorflow as tf

_BATCH_SIZE = 128
NUM_UNITS = 512
LEN_PER_SENTENCE = 4
_model_path = os.path.join(save_dir, 'model')
class Generator():


    #����key_word��
    def _build_keyword_encoder(self):
        # ������B * key_word_length * ����������
        self.keyword = tf.placeholder(
            shape=[_BATCH_SIZE, None, WORD_VEC_DIM],
            dtype=tf.float32,
            name="keyword")
        # ������ B * 1
        self.keyword_length = tf.placeholder(shape=[_BATCH_SIZE],
                                             dtype=tf.int32,
                                             name="keyword_length")  # keyword����
        #
        _, states = tf.nn.bidirectional_dynamic_rnn(
            cell_fw=tf.contrib.rnn.GRUCell(num_units=NUM_UNITS / 2),
            cell_bw=tf.contrib.rnn.GRUCell(num_units=NUM_UNITS / 2),
            inputs=self.keyword,
            sequence_length=self.keyword_length,
            dtype=tf.float32,
            scope="keyword_encoder")
        states_fw, states_bw = states
        self.keyword_state = tf.concat([states_fw, states_bw], axis=-1)  # concat˫���input
        tf.TensorShape([_BATCH_SIZE, NUM_UNITS]).assert_same_rank(self.keyword_state.shape)

    #�����ﾳ����
    def _build_context_encoder(self):
        #����ΪB * length_per_sentence(ÿ������ľ�����^��ʼ����$��β, �������볤�ȴ����9) * unit
        self.context = tf.placeholder(
            shape=[_BATCH_SIZE, None, WORD_VEC_DIM],
            dtype=tf.float32,
            name="context")
        self.context_length = tf.placeholder(shape=[_BATCH_SIZE],
                                             dtype=tf.int32,
                                             name="context_length")

        outputs, _ = tf.nn.bidirectional_dynamic_rnn(
            cell_fw=tf.contrib.rnn.GRUCell(num_units=NUM_UNITS / 2),
            cell_bw=tf.contrib.rnn.GRUCell(num_units=NUM_UNITS / 2),
            inputs=self.context,
            sequence_length=self.context_length,
            dtype=tf.float32,
            scope="context_encoder")
        output_fw, output_bw = outputs
        self.context_output = tf.concat([output_fw, output_bw], axis=-1)
        tf.TensorShape([_BATCH_SIZE, None, NUM_UNITS]).assert_same_rank(self.context_output.shape)

    def _build_decoder(self):
        with tf.name_scope("decoder"):
            attention_mechanism = tf.contrib.seq2seq.BahdanauAttention(
                num_units=NUM_UNITS,
                memory=self.context_output, # �� ���� encoder ��������Ϊ���
                memory_sequence_length=self.context_length,
                name="BahdanauAttention",
            )
            # ������GRU��Ԫ��ATTENSTTION��װ
            decoder_rnn_cell = tf.contrib.seq2seq.AttentionWrapper( # decoder ��RNN��Ԫ
                cell=tf.contrib.rnn.GRUCell(NUM_UNITS),
                attention_mechanism=attention_mechanism,
                initial_cell_state=self.keyword_state,
                name="decoder_rnn_cell",
            )
            # ������ѵ��
            self.decoder_input = tf.placeholder(
                shape= [_BATCH_SIZE, None, NUM_UNITS],
                dtype=tf.float32,
                name="input"
            )
            self.decoder_length = tf.placeholder(
                shape= [_BATCH_SIZE],
                dtype = tf.int32,
                name='length'
            )
            print(self.keyword_state)
            decoder_init_state = decoder_rnn_cell.zero_state(dtype=tf.float32, batch_size=_BATCH_SIZE).clone(cell_state=self.keyword_state)
            self.decoder_output, _ = tf.nn.dynamic_rnn(
                cell=decoder_rnn_cell,
                inputs=self.decoder_input,
                sequence_length=self.decoder_length,
                initial_state=decoder_rnn_cell.zero_state(dtype=tf.float32, batch_size=_BATCH_SIZE),
                dtype=tf.float32
            )
        

    def _build_soft_max(self):
        with tf.name_scope("softmax"):
            weight = tf.Variable(
                initial_value=tf.random_normal(
                shape=(NUM_UNITS, len(self.char_dict)),
                stddev=0.08,
                mean=0.00,
                dtype=tf.float32
            ),
                dtype=tf.float32,
                name="weight")
            bias= tf.Variable(
                initial_value=tf.zeros(shape=(len(self.char_dict)), dtype=tf.float32),
                dtype=tf.float32,
                name="bias"
            )
            #tf.TensorShape([_BATCH_SIZE, LEN_PER_SENTENCE + 1, NUM_UNITS]).assert_same_rank(self.decoder_output.shape)
            reshaped_output = tf.reshape(self.decoder_output, [_BATCH_SIZE * (LEN_PER_SENTENCE + 1), NUM_UNITS])
            self.probs = tf.nn.softmax(tf.matmul(reshaped_output, weight) + bias, axis=-1)
            #tf.TensorShape([_BATCH_SIZE, len(self.char_dict)]).assert_same_rank(self.probs.shape)
    #ѵ��
    def _build_optimizer(self):
        lr = 1e-3
        # �����label ��batch��������������batch������label��Ȼ���ǵڶ���label�������ֹ��label
        self.labels = tf.placeholder(shape=[None],
                                                 dtype=tf.int32,
                                                 name="labels")
        label = tf.one_hot(self.labels, len(self.char_dict))
        self.mean_loss = tf.reduce_mean(tf.reduce_max(-label * tf.math.log(self.probs + 0.000001), axis=-1), axis=-1)
        self.train_op = tf.train.AdamOptimizer(learning_rate=lr).minimize(
            self.mean_loss)
    # ���캯���е���
    def _build_layers(self):
        self._build_keyword_encoder()
        self._build_context_encoder()
        self._build_decoder()
        self._build_soft_max()
        self._build_optimizer()

    # ���캯��
    def __init__(self):
        self.char_dict = wordDict()  # �ֵ䳤��,֮�����
        self.char2vec = word2Vec()
        self._build_layers()  # ���ɽṹ
        self.saver = tf.train.Saver(tf.global_variables())  # ����ģ��

    def generate(self, keywords, context):
        '''
            ���룺
                keyword��
                keyword_length
                context
                context_length
                ��label������
                �������ɵľ���������һ��
                keyword = ["��"�� "��"�� ����� ��ʵ��]
                context = ["^"] -> ["^�������º�ʱ��$"] -> ["^�������º�ʱ��$����֪����$"]
                ret =
        '''
        pron_dict = PronDict()
        context = "^" + context + "$"
        with tf.Session() as sess:
            ckpt = tf.train.get_checkpoint_state(save_dir)
            #trained = False
            print(1)
            self.saver.restore(sess, 'C:\\Users\l\Desktop\python\ChinesePoetryGeneration\save\model')
            trained = True
            if not trained:
                print("Ҫ�ǵ���ѵģ��Ŷ")
                sys.exit(1)
            for i in range(len(keywords)):
                keyword = keywords[i]
                kw, kw_l = self.get_data_length([keyword for _ in range(_BATCH_SIZE)])
                ct, ct_l = self.get_data_length([context for _ in range(_BATCH_SIZE)])
                dd, dd_l = self.get_decoder_length([context for _ in range(_BATCH_SIZE)])
                feed_dict = {
                    self.keyword: kw,
                    self.keyword_length: kw_l,
                    self.context: ct,
                    self.context_length: ct_l,
                    self.decoder_length: dd_l,
                    self.decoder_input: dd
                }
                prob = sess.run(self.probs, feed_dict=feed_dict)
                for j in range(LEN_PER_SENTENCE):
                    prob_lists = self.gen_prob_list(prob[j], context, pron_dict)
                    char = self.char_dict.int2word(prob_lists.index(max(prob_lists)))
                    #print(char)
                    context+=char
                    context += ' '
                context += end_of_sentence()
        return context[1:].split(end_of_sentence())

    def gen_prob_list(self, probs, context, pron_dict):#param probs:softmax����ĸ��ʷֲ� context:�����ɵľ��� pron_dict:�����ֵ�
        prob_list = probs.tolist()#array->list ȡ����
        prob_list[0]*=0
        prob_list[-1]*=0#��β��0
        text = context
        text = text.replace(' ', '')
        #print(text)
        idx = len(text)
        used_chars = set(ch for ch in context)
        for i in range(1, len(prob_list) - 1):
            word = self.char_dict.int2word(i)
            word_length = len(word)
            if word_length == 0:
                continue
            first_ch = word[0]
            last_ch = word[-1]#ĩβ����
            #idx��list�±�Ҫ��1(��Ϊ��start_of_sentenceΪcontext[0])
            #һ��7����һ��end e.g:a[1]-a[7]=char a[8]=$
            # Penalize used characters. �ִ��ظ�
            if first_ch in used_chars or last_ch in used_chars:
                prob_list[i] *= 0.01

            #���ִ���Ĭ�ϴ����Ϊ2��ֱ�Ӹ������㣬ȷ������
            if(idx == 6 or idx == 14 or idx == 22 or idx == 30) and word_length == 1:
                prob_list[i] *= 0
                continue
            if(idx == 7 or idx == 15 or idx == 23 or idx == 31) and (word_length == 2):
                prob_list[i] *= 0
                continue
            #�����Ѻ�ϡ�ƽ��ͬ����Ժ�����ϸ�ģ���ȷ��������ʽ��������
            if (idx == 16-word_length or idx == 32-word_length) and \
                    not pron_dict.co_rhyme(last_ch, text[7]):
                prob_list[i] *= 1e-7#��Ѻ�Ͽ��Լ�������Ȩ�أ���֤�Ӿ�Ч��

            if idx > 2 and idx % 8 == 2 and \
                    not pron_dict.counter_tone(text[2], first_ch) and word_length == 1:
                prob_list[i] *= 0.4
            if idx > 2 and idx % 8 == 1 and \
                    not pron_dict.counter_tone(text[2], last_ch) and word_length == 2:
                prob_list[i] *= 0.4

            if (idx % 8  == 4 or idx % 8 == 6) and \
                    not pron_dict.counter_tone(text[idx - 2], first_ch) and word_length == 1:
                prob_list[i] *= 0.4
            if (idx % 8  == 3 or idx % 8 == 5) and \
                    not pron_dict.counter_tone(text[idx - 2], last_ch) and word_length == 2:
                prob_list[i] *= 0.4
        return prob_list

    def train(self, epoch):
        '''
            ���룺
                keyword��
                keyword_length
                context
                context_length
                ��label������
                �������ɵľ���������һ��
                keyword = ["��"�� "����"�� "¥"�� "�ʹ�"]
                context = ["^", "^�������º�ʱ��$", "�������º�ʱ��$����֪����$"]
                label = ["�������º�ʱ��$", "����֪����$", "С¥��ҹ�ֶ���$"]
        '''
        with tf.Session() as sess:
            ckpt = tf.train.get_checkpoint_state(save_dir)
            if not ckpt or not ckpt.model_checkpoint_path:
                sess.run(tf.global_variables_initializer())
                sess.run(tf.local_variables_initializer())
            else:
                self.saver.restore(sess, ckpt.model_checkpoint_path)
            for i in range(epoch):
                cnt = 0
                for keyword, context, label in batch_train_data(_BATCH_SIZE): # _BATCH_SIZE * l; _BATCH_SIZE * length; _BATCH_SIZE * length
                    # ���ѭ������� ����ʫ�� / _BATCH_SIZE��
                    if len(keyword) < _BATCH_SIZE:
                        break
                    kw, kw_l = self.get_data_length(keyword)
                    ct, ct_l = self.get_data_length(context)
                    dd, dd_l = self.get_data_length(label)
                    lb = self.get_label(label)
                    feed_dict = {
                        self.keyword: kw,
                        self.keyword_length :kw_l,
                        self.context:ct,
                        self.context_length: ct_l,
                        self.labels :lb,
                        self.decoder_length:dd_l,
                        self.decoder_input:dd
                    }
                    #print(np.shape(lb))
                    _, loss = sess.run([self.train_op, self.mean_loss], feed_dict=feed_dict)
                    cnt+=1
                    print(cnt, loss)
                    #print("it is trainning!!!loss:%f", loss)
                    if cnt % 64 == 0:
                        self.saver.save(sess, _model_path)
                        print("epoch: %d, have_trained_batch: %d, loss: %f"%(i, cnt, loss))

    def get_decoder_length(self, a):
        assert type(a) == list
        assert len(a) == _BATCH_SIZE
        for i in range(len(a)):
            if len(a[i]) == 1:
                a[i] = "$"
                continue
            l = len(a[i])
            for j in range(l - 2, -1, -1):
                if a[i][j] == '$' or a[i][j] == '^':
                    a[i] = a[i][j + 1:]
                    break
        ret, ret_l = self.get_data_length(a)
        return ret, ret_l

    def get_data_length(self, a):
        '''
                keyword = ["��"�� "����"�� "¥"�� "�ʹ�"]
                context = ["^", "^�������º�ʱ��$", "^�������º�ʱ��$����֪����$"]
                setence = ["�������º�ʱ��$", "�������º�ʱ��$����֪����$", "�������º�ʱ��$����֪����$С¥��ҹ�ֶ���$"]
        '''
        assert type(a) == list
        assert len(a) == _BATCH_SIZE
        # a ���ַ�������
        for i in range(_BATCH_SIZE):
            text = a[i]
            for ch in text:
                if ch == '^':
                    text = text.replace(ch, ch+' ')
                if ch == '$':
                    text = text.replace(ch, ' '+ch+' ')
            text = text.strip()
            text = text.split()
            a[i] = text
        maxtime = max(map(len, a))
        ret = np.zeros(shape=[_BATCH_SIZE, maxtime, WORD_VEC_DIM], dtype=np.float32)
        length = np.zeros(shape=[_BATCH_SIZE, 1])
        for i in range(_BATCH_SIZE):
            length[i] = len(a[i])
            for j in range(maxtime):
                if j < len(a[i]):
                    ret[i][j] = self.char2vec.get_vect(a[i][j])
                else:
                    ret[i][j] = self.char2vec.get_vect(end_of_sentence()) #��ȷ��
        length = np.reshape(length, [length.shape[0]])
        return ret, length
    def get_label(self, a):
        '''label = ["����$", "��$", "С$"]
            label = [id(chun), id(��), id(С), id(��), id($), id($), id($), id($), id($)]
        '''
        #print(type(a))
        assert type(a) == list
        assert len(a) == _BATCH_SIZE
        maxtime = max(map(len, a))
        ret = np.zeros(shape=(_BATCH_SIZE * maxtime), dtype=np.int32)
        tmp = 0
        for i in range(_BATCH_SIZE):
            for j in range(maxtime):
                if(len(a[i]) < j + 1):
                    ret[tmp] = self.char_dict.word2int(end_of_sentence())
                else:
                    ret[tmp] = self.char_dict.word2int(a[i][j])
                tmp+=1
        return ret
if __name__ == "__main__":
    generator = Generator()
    #generator.train(epoch = 1)
    poem = generator.generate(["��", "��", "��"], "���� ױ�� һ�� ��")
    print(poem)