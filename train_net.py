from __future__ import print_function, division
import os
import torch
import numpy as np

from torch.utils.data import Dataset, DataLoader
from torch.utils.data import sampler
from torch.utils.data import random_split
from torchvision import transforms, utils, models
from PIL import Image
from cross_validation import k_folds

import pandas as pd


import pdb

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F  # useful stateless functions

import nets 
import transformations
from PathologyDataset import PathologyDataset
#### Settings 

USE_GPU = True
dtype = torch.float32 # we will be using float throughout this tutorial

if USE_GPU and torch.cuda.is_available():
	device = torch.device('cuda')
else:
	device = torch.device('cpu')

# Constant to control how frequently we print train loss
print_every = 2

print('using device:', device)


def check_accuracy(loader, model, train, filename=None):
	"""evaluted model and report accuracy

	args:
		loader: pytorch dataloader
		model: pytorch module
		train (boolean): in training mode or not

	return:
		acc: accuracy of evaluation 
	"""
	num_correct = 0
	num_samples = 0
	model.eval()  # set model to evaluation mode
	
	if train:
		print('Checking accuracy on validation set')
	else:
		print('Final Evaluation') 

	with torch.no_grad():
		for x, y in loader:
			x = x.to(device=device, dtype=dtype)  # move to device, e.g. GPU
			y = y.to(device=device, dtype=torch.long)
			scores = model(x)
			_, preds = scores.max(1)
			num_correct += (preds == y).sum()
			num_samples += preds.size(0)
			if not train:
				p = F.softmax(scores).data.cpu().numpy()
				c0, c1, c2, c3 = np.split(p, 4, axis = 1)
				y = y.data.cpu().numpy()
				preds = preds.data.cpu().numpy()
				results_dict = {'p0': c0.squeeze(), 
								'p1': c1.squeeze(), 
								'p2': c2.squeeze(), 
								'p3': c3.squeeze(), 
								'label': y, 
								'pred': preds, 
								'eval': preds == y}
				results = pd.DataFrame.from_dict(results_dict)
				results.to_csv(filename, index = False)

		
		acc = float(num_correct) / num_samples
		print('Got %d / %d correct (%.2f)' % (num_correct, num_samples, 100 * acc))
		print()
		return acc


def train_loop(model, loaders, optimizer, epochs=10, filename=None):
	"""
	Train a model on CIFAR-10 using the PyTorch Module API.
	
	Inputs:
	- model: A PyTorch Module giving the model to train.
	- optimizer: An Optimizer object we will use to train the model
	- epochs: (Optional) A Python integer giving the number of epochs to train for
	
	Returns: Nothing, but prints model accuracies during training.
	"""
	if torch.cuda.device_count() > 1:
		print("Let's use", torch.cuda.device_count(), "GPUs!")
		model = nn.DataParallel(model)
	
	model = model.to(device=device)  # move the model parameters to CPU/GPU
	loader_train = loaders['train']
	loader_val = loaders['val']
	print('training begins')
	for e in range(epochs):
		for t, (x, y) in enumerate(loader_train):
			model.train()  # put model to training mode

			x = x.to(device=device, dtype=dtype)  # move to device, e.g. GPU
			y = y.to(device=device, dtype=torch.long)

			scores = model(x)
			loss = F.cross_entropy(scores, y)

			# Zero out all of the gradients for the variables which the optimizer
			# will update.
			optimizer.zero_grad()

			# This is the backwards pass: compute the gradient of the loss with
			# respect to each  parameter of the model.
			loss.backward()

			# Actually update the parameters of the model using the gradients
			# computed by the backwards pass.
			optimizer.step()
			if t % print_every == 0 :
				print('Epoch %d of %d, Iteration %d, loss = %.4f' % (e+1, epochs, t+1, loss.item()))
				print()

		acc = check_accuracy(loader_val, model, train=True, filename=None)

	print()
	acc = check_accuracy(loader_val, model, train=False, filename=filename)
	return acc


def train_network(ssh = True):
	NUM_TRAIN = 360
	NUM_VAL = 40
	batch_size = 32
	learning_rate = 1e-3
	k = 10
	num_classes = 4

	if ssh:
		root_dir='/workspace/path_data/Part-A_Original'
	else:
		root_dir='/Users/admin/desktop/path_pytorch/Part-A_Original'

	# path_data_train and path_data_val should have different transformation (path_data_val should not apply data augmentation)
	# therefore we shuffle path_data_train and copy its shuffled image ids and corresponding labels over to path_data_val
	path_data_train = PathologyDataset(csv_file='microscopy_ground_truth.csv', root_dir=root_dir, shuffle = True, transform=transformations.multiresize())
	path_data_val = PathologyDataset(csv_file='microscopy_ground_truth.csv', root_dir=root_dir, shuffle = False, transform=transformations.val())

	path_data_val.img_ids = path_data_train.img_ids.copy()
	path_data_val.img_labels = path_data_train.img_labels.copy()

	# initialize acc vector for cv results 
	acc = np.zeros((k,))
	
	# fold counter
	counter = 0

	# k-fold eval
	for train_idx, test_idx in k_folds(n_splits = k):
		print('training and evaluating fold ', counter)
		### result file
		filename = 'results_' + str(counter) + '.csv'
		
		### initialize data loaders
		loader_train = torch.utils.data.DataLoader(dataset = path_data_train, batch_size = batch_size, sampler = sampler.SubsetRandomSampler(train_idx))
		loader_val = torch.utils.data.DataLoader(dataset = path_data_val, batch_size = 40, sampler = sampler.SubsetRandomSampler(test_idx))
		loaders = {'train': loader_train, 'val': loader_val}
		### initialize model
		model = nets.resnet50_train(num_classes)
		print(model)
		print()

		for name, p in model.named_parameters():
			print(name, p.requires_grad)

		### initialize optimizer
		optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()),lr = learning_rate)
		
		### call training/eval
		acc[counter] = train_loop(model, loaders, optimizer, epochs=200, filename=filename)

		### update counter
		counter+=1
	
	print('k-fold CV accuracy: ', acc)
	print('final mean accuracy: ', np.mean(acc))

def test_cv(dset1, dset2):
	# make sure the two datasets are identical in ids and labels
	assert np.all(np.equal(dset1.img_ids, dset2.img_ids))
	assert np.all(np.equal(dset1.img_labels, dset2.img_labels))

train_network()
