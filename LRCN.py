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
from numpy.random import *

class Alex(chainer.Chain):

    """Single-GPU AlexNet without partition toward the channel axis."""

    insize = 227

    def __init__(self, length, n_outputs, n_units=2048, train=True):
        super(Alex, self).__init__(
            conv1=L.Convolution2D(3,  96, 11, stride=4),
            conv2=L.Convolution2D(96, 256,  5, pad=2),
            conv3=L.Convolution2D(256, 384,  3, pad=1),
            conv4=L.Convolution2D(384, 384,  3, pad=1),
            conv5=L.Convolution2D(384, 256,  3, pad=1),
            fc6=L.Linear(9216, 4096),
            fc7=L.Linear(4096,n_units),
            l8=L.LSTM(n_units, n_units),
            fc9=L.Linear(n_units,n_outputs)
        )
        self.train = True

    def __forward(self, x, train=True):
        h = F.max_pooling_2d(F.relu(
            F.local_response_normalization(self.conv1(x))), 3, stride=2)
        h = F.max_pooling_2d(F.relu(
            F.local_response_normalization(self.conv2(h))), 3, stride=2)
        h = F.relu(self.conv3(h))
        h = F.relu(self.conv4(h))
        h = F.max_pooling_2d(F.relu(self.conv5(h)), 3, stride=2)
        h = F.relu(self.fc6(h))
        h = F.relu(self.fc7(h))
        h = F.relu(self.l8(h))
        h = self.fc9(h)
        return h

    def forward(self, x_data, y_data, train=True, gpu=-1):

        if gpu >= 0:
            x_data = cuda.to_gpu(x_data)
            y_data = cuda.to_gpu(y_data)
        x, t = Variable(x_data), Variable(y_data)
        y = self.__forward(x, train=train)
        return F.softmax_cross_entropy(y, t), F.accuracy(y, t)

    def reset_state(self):
        self.l8.reset_state()

    def predict(self, x_data, gpu=-1, train=False):
        if gpu >= 0:
            x_data = cuda.to_gpu(x_data)
        x = Variable(x_data)

        y = self.__forward(x, train=train)

        return F.softmax(y).data




class LRCN_Hybrid:
    def __init__(self, data, target, n_outputs=5, length=4096, gpu=-1):

        self.model = Alex(length, n_outputs)
        self.model_name = 'HybridModelPlanted'
        self.dump_name = 'HybridModel'

        if gpu >= 0:
            self.model.to_gpu()

        self.gpu = gpu

        self.length = length
        self.dim = n_outputs

        self.x_feature = data
        self.y_feature = target

        self.optimizer = optimizers.Adam()
        self.optimizer.setup(self.model)

    def predict(self):
        return self.model.predict(self.x_test, gpu=self.gpu)

    def train_and_test(self, n_epoch=200, batch=50):
        epoch = 1
        win = 0
        win_last = 0
        for seq in range(n_epoch):

            self.model.reset_state()

            motionIndex = [[] for y in range(batch)]
            for i in range(batch):
                randomMotion1 = randint(len(self.x_feature))
                randomMotion2 = randint(len(self.x_feature[randomMotion1]))
                randomMotion3 = randint(len(self.x_feature[randomMotion1][randomMotion2]))
                motionIndex[i].append(randomMotion1)
                motionIndex[i].append(randomMotion2)
                motionIndex[i].append(randomMotion3)                

            for j in range(len(self.x_feature[randomMotion1][randomMotion2][randomMotion3])):
                x = []
                t = []
                for k, index in enumerate(motionIndex):
                    x.append(self.x_feature[index[0]][index[1]][index[2]][j])
                    t.append(index[0])
                x = np.asarray(x, dtype=np.float32)
                t = np.asarray(t, dtype=np.int32)

                self.optimizer.zero_grads()
                loss, acc = self.model.forward(x, t, gpu=self.gpu)
                loss.backward()
                self.optimizer.update()
                print '=================='
                print epoch
                print loss.data


            # prediction
            if epoch%1 ==0:
                self.model.reset_state()
                randomMotion1 = randint(len(self.x_feature))
                randomMotion2 = randint(len(self.x_feature[randomMotion1]))
                randomMotion3 = randint(len(self.x_feature[randomMotion1][randomMotion2]))
                sequence = self.x_feature[randomMotion1][randomMotion2][randomMotion3]

                payload = np.zeros(self.dim)
                for i, image in enumerate(sequence):
                    x = np.asarray(image[np.newaxis, :], dtype=np.float32)
                    result = cuda.to_cpu(self.model.predict(x, gpu=self.gpu, train=False))

                    payload += result[0]/len(sequence)
                if randomMotion1 == np.argmax(payload):
                    win += 1
                if randomMotion1 == np.argmax(result[0]):
                    win_last += 1
                print 'Answer Average:', randomMotion1, ' Pred:', np.argmax(payload), ',',np.max(payload)*100,'%'
                print 'softmax', payload
                print 'Average winning ratio: ', win,'/',epoch/1
                print 'Answer Last:', randomMotion1, ' Pred:', np.argmax(result[[0]]), ',',np.max(result[0])*100,'%'
                print 'softmax', result[0]                
                print 'Last winning ratio: ', win_last,'/',epoch/1
                print '=================================='

            epoch += 1



    def dump_model(self,name):
        self.model.to_cpu()
        pickle.dump(self.model, open(self.dump_name+name, 'wb'), -1)

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