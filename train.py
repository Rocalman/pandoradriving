import argparse
import importlib
import os
import sys
import time
import datetime

import numpy as np
import scipy

import provider_leibao as provider
import tensorflow as tf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'models'))
sys.path.append(os.path.join(BASE_DIR, 'models_dep'))

parser = argparse.ArgumentParser()
parser.add_argument('--gpu', type=int, default=0,
                    help='GPU to use [default: GPU 0]')
parser.add_argument('--model', default='nvidia_pn',
                    help='Model name [default: nvidia_pn]')
parser.add_argument('--add_lstm', type=bool, default=False,
                    help='Introduce LSTM mechanism in netowrk [default: False]')
parser.add_argument('--log_dir', default='logs',
                    help='Log dir [default: logs]')
parser.add_argument('--max_epoch', type=int, default=250,
                    help='Epoch to run [default: 250]')
parser.add_argument('--batch_size', type=int, default=8,
                    help='Batch Size during training [default: 8]')
parser.add_argument('--learning_rate', type=float, default=0.001,
                    help='Learning rate during training [default: 0.001]')
parser.add_argument('--momentum', type=float, default=0.9,
                    help='Initial learning rate [default: 0.9]')
parser.add_argument('--optimizer', default='adam',
                    help='adam or momentum [default: adam]')
parser.add_argument('--decay_step', type=int, default=200000,
                    help='Decay step for lr decay [default: 200000]')
parser.add_argument('--decay_rate', type=float, default=0.7,
                    help='Decay rate for lr decay [default: 0.8]')
parser.add_argument('--add_orientations', type=bool, default=False,
                    help='Add the orientations in netowrk [default: False]')
parser.add_argument('--loss_function', default='mae',
                    help='loss function [default: mae]')
FLAGS = parser.parse_args()

BATCH_SIZE = FLAGS.batch_size
MAX_EPOCH = FLAGS.max_epoch
LEARNING_RATE = FLAGS.learning_rate
OPTIMIZER = FLAGS.optimizer
BASE_LEARNING_RATE = FLAGS.learning_rate
GPU_INDEX = FLAGS.gpu
MOMENTUM = FLAGS.momentum
DECAY_STEP = FLAGS.decay_step
DECAY_RATE = FLAGS.decay_rate
ADD_LSTM = FLAGS.add_lstm
ADD_ORI = FLAGS.add_orientations

BN_INIT_DECAY = 0.5
BN_DECAY_DECAY_RATE = 0.5
BN_DECAY_DECAY_STEP = float(DECAY_STEP)
BN_DECAY_CLIP = 0.99

supported_loss_func = ["mae", "mse", "stlossmse", "stloss2"]
assert (FLAGS.loss_function in supported_models)
LOSS_FUNC = FLAGS.loss_function

supported_models = ["nvidia_io", "nvidia_pn",
                    "resnet152_io", "resnet152_pn",
                    "inception_v4_io", "inception_v4_pn",
                    "densenet169_io", "densenet169_pn","vgg16_io","nvidia_io_nvi","nvidia_io_nvi_time","nvidia_io_dep_steer_lstm",
                    "nvidia_io_steer_lstm", "nvidia_io_steer_lstm_stloss"]
# assert (FLAGS.model in supported_models)
MODEL = importlib.import_module(FLAGS.model)  # import network module
MODEL_FILE = os.path.join(BASE_DIR, 'models', FLAGS.model+'.py')
# MODEL_FILE = os.path.join(BASE_DIR, 'models_dep', FLAGS.model+'.py')

LOG_DIR = os.path.join(FLAGS.log_dir, FLAGS.model)
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
os.system('cp %s %s' % (MODEL_FILE, LOG_DIR))  # bkp of model def
os.system('cp train.py %s' % (LOG_DIR))  # bkp of train procedure
LOG_FOUT = open(os.path.join(LOG_DIR, 'log_train.txt'), 'w')
LOG_FOUT.write(str(FLAGS)+'\n')


def log_string(out_str):
    LOG_FOUT.write(out_str+'\n')
    LOG_FOUT.flush()
    print(out_str)


def get_learning_rate(batch):
    learning_rate = tf.train.exponential_decay(
                        BASE_LEARNING_RATE,  # Base learning rate.
                        batch * BATCH_SIZE,  # Current index into the dataset.
                        DECAY_STEP,          # Decay step.
                        DECAY_RATE,          # Decay rate.
                        staircase=True)
    learning_rate = tf.maximum(learning_rate, 0.00001)  # CLIP THE LEARNING RATE!
    return learning_rate


def get_bn_decay(batch):
    bn_momentum = tf.train.exponential_decay(
                      BN_INIT_DECAY,
                      batch*BATCH_SIZE,
                      BN_DECAY_DECAY_STEP,
                      BN_DECAY_DECAY_RATE,
                      staircase=True)
    bn_decay = tf.minimum(BN_DECAY_CLIP, 1 - bn_momentum)
    return bn_decay


def train():
    with tf.Graph().as_default():
        with tf.device('/gpu:'+str(GPU_INDEX)):
            if '_pn' in MODEL_FILE:
                data_input = provider.Provider()
                imgs_pl, pts_pl, labels_pl = MODEL.placeholder_inputs(BATCH_SIZE)
                imgs_pl = [imgs_pl, pts_pl]
            elif '_io' in MODEL_FILE:
                data_input = provider.Provider()
                if ADD_ORI:
                    imgs_pl, labels_pl = MODEL.placeholder_inputs_img5(BATCH_SIZE)
                else:
                    imgs_pl, labels_pl = MODEL.placeholder_inputs(BATCH_SIZE)
            else:
                raise NotImplementedError

            is_training_pl = tf.placeholder(tf.bool, shape=())
            print(is_training_pl)

            # Note the global_step=batch parameter to minimize.
            # That tells the optimizer to helpfully increment the 'batch'
            # parameter for you every time it trains.
            # batch = tf.Variable(0)
            batch = tf.get_variable('batch', [],
                initializer=tf.constant_initializer(0), trainable=False)
            bn_decay = get_bn_decay(batch)
            tf.summary.scalar('bn_decay', bn_decay)

            pred = MODEL.get_model(imgs_pl, is_training_pl, bn_decay=bn_decay)

            if LOSS_FUNC == "mae":
                loss = MODEL.get_loss_mae(pred, labels_pl)
            elif LOSS_FUNC == "mse":
                loss = MODEL.get_loss_mse(pred, labels_pl)
            elif LOSS_FUNC == "stlossmse":
                loss = MODEL.get_loss_stlossmse(pred, labels_pl)
            elif LOSS_FUNC == "stloss2":
                loss = MODEL.get_loss_stloss2(pred, labels_pl)
            
            MODEL.summary_scalar(pred, labels_pl)

            # Get training operator
            learning_rate = get_learning_rate(batch)
            tf.summary.scalar('learning_rate', learning_rate)
            if OPTIMIZER == 'momentum':
                optimizer = tf.train.MomentumOptimizer(learning_rate,
                                                       momentum=MOMENTUM)
            elif OPTIMIZER == 'adam':
                optimizer = tf.train.AdamOptimizer(learning_rate)
            train_op = optimizer.minimize(loss, global_step=batch)
            # Add ops to save and restore all the variables.
            saver = tf.train.Saver()

        # Create a session
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.allow_soft_placement = True
        config.log_device_placement = False
        sess = tf.Session(config=config)

        # Add summary writers
        # merged = tf.merge_all_summaries()
        merged = tf.summary.merge_all()
        train_writer = tf.summary.FileWriter(os.path.join(LOG_DIR, 'train'),
                                             sess.graph)
        test_writer = tf.summary.FileWriter(os.path.join(LOG_DIR, 'test'))

        # Init variables
        init = tf.global_variables_initializer()
        sess.run(init, {is_training_pl: True})

        ops = {'imgs_pl': imgs_pl,
               'labels_pl': labels_pl,
               'is_training_pl': is_training_pl,
               'pred': pred,
               'loss': loss,
               'train_op': train_op,
               'merged': merged,
               'step': batch}

        eval_acc_max = 0
        eval_bef = 0
        for epoch in range(MAX_EPOCH):
            log_string('**** EPOCH %03d ****' % (epoch))
            # print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))
            sys.stdout.flush()

            train_one_epoch(sess, ops, train_writer, data_input)
            
            eval_acc = eval_one_epoch(sess, ops, test_writer, data_input)
            if eval_bef<eval_acc:
                save_path = saver.save(sess, os.path.join(LOG_DIR, "model.ckpt"))
                log_string("Model saved in file: %s" % save_path+str(epoch))
            eval_bef = eval_acc
            if eval_acc > eval_acc_max:
                eval_acc_max = eval_acc
                save_path = saver.save(sess, os.path.join(LOG_DIR, "model_best.ckpt"))
                log_string("Model saved in file: %s" % save_path)


def train_one_epoch(sess, ops, train_writer, data_input):
    """ ops: dict mapping from string to tf ops """
    is_training = True
    num_batches = data_input.num_train // BATCH_SIZE
    loss_sum = 0
    
    loss_sum_steer = 0
    loss_sum_speed = 0
    
    acc_a_sum = 0
    acc_s_sum = 0
    counter = 0

    for batch_idx in range(num_batches):
        if "_io" in MODEL_FILE:
            imgs, labels = data_input.load_one_batch(BATCH_SIZE, "train", reader_type="io", add_ori=ADD_ORI)
            if "resnet" in MODEL_FILE or "inception" in MODEL_FILE or "densenet" in MODEL_FILE or "vgg" in MODEL_FILE:
                imgs = MODEL.resize(imgs)
            feed_dict = {ops['imgs_pl']: imgs,
                         ops['labels_pl']: labels,
                         ops['is_training_pl']: is_training}
        else:
            imgs, others, labels = data_input.load_one_batch(BATCH_SIZE, "train", reader_type="pn",add_ori=ADD_ORI)
            if "resnet" in MODEL_FILE or "inception" in MODEL_FILE or "densenet" in MODEL_FILE:              
                imgs = MODEL.resize(imgs)
            feed_dict = {ops['imgs_pl'][0]: imgs,
                         ops['imgs_pl'][1]: others,
                         ops['labels_pl']: labels,
                         ops['is_training_pl']: is_training}

        summary, step, _, loss_val, pred_val = sess.run([ops['merged'],
                                                         ops['step'],
                                                         ops['train_op'],
                                                         ops['loss'],
                                                         ops['pred']],
                                                        feed_dict=feed_dict)
        train_writer.add_summary(summary, step)
        loss_sum += np.mean(np.abs(np.subtract(pred_val, labels)))          # MAE
        loss_sum_steer += np.mean(np.abs(np.subtract(pred_val, labels)))
        
        acc_a = np.abs(np.subtract(pred_val, labels)) < (5.0)
        acc_a = np.mean(acc_a)
        acc_a_sum += acc_a

        counter += 1
        if (batch_idx+1)%50 == 0:
            log_string(' -- %03d / %03d --' % (batch_idx+1, num_batches))
            log_string('loss: %f' % (loss_sum / float(50)))
            
            log_string('steer loss: %f' % (loss_sum_steer / float(50)))
            log_string('acc (angle): %f' % (acc_a_sum / float(50)))
            loss_sum = 0
            
            loss_sum_speed = 0
            loss_sum_steer = 0
            
            acc_a_sum = 0
            acc_s_sum = 0


def eval_one_epoch(sess, ops, test_writer, data_input):
    """ ops: dict mapping from string to tf ops """
    is_training = False
    loss_sum = 0
    
    loss_sum_steer = 0
    loss_sum_speed = 0

    num_batches = data_input.num_val // BATCH_SIZE
    loss_sum = 0
    acc_a_sum = 0
    acc_s_sum = 0

    for batch_idx in range(num_batches):
        if "_io" in MODEL_FILE:
            imgs, labels = data_input.load_one_batch(BATCH_SIZE, "val", reader_type="io",add_ori=ADD_ORI)
            if "resnet" in MODEL_FILE or "inception" in MODEL_FILE or "densenet" in MODEL_FILE or "vgg" in MODEL_FILE:
                imgs = MODEL.resize(imgs)
            feed_dict = {ops['imgs_pl']: imgs,
                         ops['labels_pl']: labels,
                         ops['is_training_pl']: is_training}
        else:
            imgs, others, labels = data_input.load_one_batch(BATCH_SIZE, "val",add_ori=ADD_ORI)
            if "resnet" in MODEL_FILE or "inception" in MODEL_FILE or "densenet" in MODEL_FILE:
                imgs = MODEL.resize(imgs)
            feed_dict = {ops['imgs_pl'][0]: imgs,
                         ops['imgs_pl'][1]: others,
                         ops['labels_pl']: labels,
                         ops['is_training_pl']: is_training}
        summary, step,  loss_val, pred_val = sess.run([ops['merged'],
                                                         ops['step'],
                                                         
                                                         ops['loss'],
                                                         ops['pred']],
                                                        feed_dict=feed_dict)
        test_writer.add_summary(summary, step)
        loss_sum += np.mean(np.abs(np.subtract(pred_val, labels)))
        
        loss_sum_steer += np.mean(np.abs(np.subtract(pred_val, labels)))
        
        acc_a = np.abs(np.subtract(pred_val, labels)) < (5.0)

        acc_a = np.mean(acc_a)
        acc_a_sum += acc_a

    log_string('eval mean loss: %f' % (loss_sum / float(num_batches)))
    log_string('eval mean steer loss: %f' % (loss_sum_steer / float(num_batches)))
    log_string('eval accuracy (angle): %f' % (acc_a_sum / float(num_batches)))
    return acc_a_sum / float(num_batches)


if __name__ == "__main__":
    train()
