#! -*- coding: utf-8 -*-

import chainer
import chainer.links as L

import time
import six.moves.cPickle as pickle
import numpy as np
from sklearn.datasets import fetch_mldata
from sklearn.cross_validation import train_test_split
from chainer import cuda, Variable, FunctionSet, optimizers
import chainer.functions as F
import alex
from numpy.random import *



class LSTM(chainer.Chain):
    def __init__(self, length, n_outputs, n_units=100, train=True):
        super(LSTM, self).__init__(
            l0=L.Linear(length, n_units),
            l1=L.LSTM(n_units, n_units),
            l2=L.LSTM(n_units, n_units),
            l3=L.Linear(n_units,n_outputs)
        )

    def __forward(self, x):
        h0 = self.l0(x)
        h1 = self.l1(h0)
        h2 = self.l2(h1)
        h3 = self.l3(h2)
        return h3

    def forward(self, x_data, y_data, train=True, gpu=-1):
        if gpu >= 0:
            x_data = cuda.to_gpu(x_data)
            y_data = cuda.to_gpu(y_data)
        x, t = Variable(x_data), Variable(np.asarray([y_data]))
        y = self.__forward(x)

        y.data = y.data.astype(np.float32)
        t.data = t.data.astype(np.int32)

        return F.softmax_cross_entropy(y, t), F.accuracy(y, t)

    def reset_state(self):
        self.l1.reset_state()


class LRCN:
    def __init__(self, data, target, length, n_outputs, gpu=-1):

        self.model = LSTM(length, n_outputs)
        self.model_name = 'LSTM_Model'

        if gpu >= 0:
            self.model.to_gpu()

        self.gpu = gpu

        self.length = length
        self.dim = n_outputs

        self.x_feature = data
        self.y_feature = target

        # lossが発散したので学習率を変更できるように
        self.optimizer = optimizers.Adam()
        self.optimizer.setup(self.model)

    def predict(self):

        return self.model.predict(self.x_test, self.y_test, gpu=self.gpu)

    def feature(self):
        featureImage = [[] for y in range(self.x_feature.shape[0])]
        payload = [[]]
        for i, motion in enumerate(self.x_feature):
            for j, image in enumerate(motion):
                payload[0] = image
                payload = np.array(payload, np.float32)
                print 'payload:',payload
                print 'payload.dtype', payload.dtype
                payload.astype(np.float32)
                print 'payload.dtype', payload.dtype
                featureImage[i].append(self.model.feature(payload, gpu=self.gpu).data)
                #featureImage[i] = self.model.feature(motion, gpu=self.gpu).data

            #for j, image in enumerate(motion):
            #    print 'image', image.shape
            #    featureImage[i][j] = self.model.feature(image, gpu=self.gpu)
        return featureImage

    def train_and_test(self, n_epoch=200, batchsize=100):
        epoch = 1
        best_accuracy = 0
        answer = np.zeros(self.dim)

        for seq in range(n_epoch):
            sum_train_accuracy = 0
            sum_train_loss = 0
            print 'epoch: ',epoch
            randomMotion = randint(self.dim)
            sequence = self.x_feature[randomMotion][randint(len(self.x_feature[randomMotion]))]
            for i, image in enumerate(sequence):
                answer[randomMotion] = 1.
                image2 = [[]]
                image2[0] = image
                x = np.asarray(image2)   # i文字目を入力に
                t = np.asarray(randomMotion) # i+1文字目を正解に

                loss, acc = self.model.forward(x, t)  # lossの計算
                loss.backward()
                self.optimizer.update
                self.model.zerograds()
                answer = np.zeros(self.dim)

                sum_train_loss += float(cuda.to_cpu(loss.data))
                sum_train_accuracy += float(cuda.to_cpu(acc.data))
                print 'loss', loss.data
                print 'acc', acc.data
                print 'train mean loss={}, accuracy={}'.format(sum_train_loss/len(self.y_feature), sum_train_accuracy/len(self.y_feature))

                # evaluation
                sum_test_accuracy = 0
                sum_test_loss = 0
                for i in range(3):
                    randomMotion = randint(self.dim)
                    sequence = self.x_feature[randomMotion][randint(len(self.x_feature[randomMotion]))]
                    for i, image in enumerate(sequence):
                        answer[randomMotion] = 1
                        image2 = [[]]
                        image2[0] = image
                        x = np.asarray(image2)   # i文字目を入力に
                        t = np.asarray(randomMotion) # i+1文字目を正解に
                        loss, acc = self.model.forward(x, t)  # lossの計算
                        answer = np.zeros(self.dim)
                        sum_test_loss += float(cuda.to_cpu(loss.data))
                        sum_test_accuracy += float(cuda.to_cpu(acc.data))

                    print 'test mean loss={}, accuracy={}'.format(sum_test_loss/len(self.y_feature), sum_test_accuracy/len(self.y_feature))

                epoch += 1


    def dump_model(self):
        self.model.to_cpu()
        pickle.dump(self.model, open(self.model_name, 'wb'), -1)

    def load_model(self):
        self.model = pickle.load(open(self.model_name,'rb'))
        if self.gpu >= 0:
            self.model.to_gpu()
        self.optimizer.setup(self.model)

    def test(self,gpu=0):
        sum_test_loss = 0
        sum_test_accuracy = 0
        x_batch=self.x_test
        y_batch=self.y_test
        loss, acc = self.model.forward(x_batch, y_batch, train=True, gpu=self.gpu)
        real_batchsize=len(x_batch)
        sum_test_loss += float(cuda.to_cpu(loss.data)) * real_batchsize
        sum_test_accuracy += float(cuda.to_cpu(acc.data)) * real_batchsize
        print 'test mean loss={}, accuracy={}'.format(sum_test_loss/self.n_test, sum_test_accuracy/self.n_test)
        print(real_batchsize)
        print(sum_test_accuracy)
