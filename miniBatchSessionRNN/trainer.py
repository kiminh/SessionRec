# import lib
from evaluation import *
import time
import torch
import numpy as np
import os
from dataset import *


class Trainer(object):
	def __init__(self, model, train_data, eval_data, optim, use_cuda, loss_func, topk, args):
		self.model = model
		self.train_data = train_data
		self.eval_data = eval_data
		self.optim = optim
		self.loss_func = loss_func
		self.topk = topk
		self.evaluation = Evaluation(self.model, self.loss_func, use_cuda, self.topk)
		self.device = torch.device('cuda' if use_cuda else 'cpu')
		self.args = args

	def train(self, start_epoch, end_epoch, batch_size, start_time=None):
		if start_time is None:
			self.start_time = time.time()
		else:
			self.start_time = start_time

		for epoch in range(start_epoch, end_epoch + 1):
			print("*"*10, epoch, "*"*5)
			st = time.time()
			train_loss = self.train_epoch(epoch, batch_size)
			loss, recall, mrr = self.evaluation.eval(self.train_data, batch_size)
			print("train Epoch: {}, train loss: {:.4f},  loss: {:.4f},recall: {:.4f}, mrr: {:.4f}, time: {}".format(epoch, train_loss, loss, recall, mrr, time.time() - st))

			loss, recall, mrr = self.evaluation.eval(self.eval_data, batch_size)
			print("Epoch: {}, loss: {:.4f}, recall: {:.4f}, mrr: {:.4f}, time: {}".format(epoch, loss, recall, mrr, time.time() - st))
			checkpoint = {
				'model': self.model.state_dict(),
				'args': self.args,
				'epoch': epoch,
				'optim': self.optim,
				'loss': loss,
				'recall': recall,
				'mrr': mrr
			}
			model_name = os.path.join(self.args.checkpoint_dir, "model_{0:05d}.pt".format(epoch))
			torch.save(checkpoint, model_name)
			print("Save model as %s" % model_name)

	def train_epoch(self, epoch, batch_size):
		self.model.train()
		losses = []

		def reset_hidden(hidden, mask):
			"""Helper function that resets hidden state when some sessions terminate"""
			if len(mask) != 0:
				hidden[:, mask, :] = 0
			return hidden
	   
		# dataloader = DataLoader(self.train_data, batch_size)
		dataloader = self.train_data

		hidden = self.model.init_hidden()
		for idx_input, idx_target, mask in dataloader:
			idx_input = idx_input.to(self.device)
			idx_target = idx_target.to(self.device)
			self.optim.zero_grad()
			
			hidden = self.model.init_hidden()
			# hidden = reset_hidden(hidden, mask).detach()
			# hidden = reset_hidden(hidden, mask).detach()
			# print("input size", input.size())
			logit, hidden = self.model(idx_input, hidden)
			# output sampling
			# print("logit size", logit.size())
			logit_sampled = logit[:, idx_target.view(-1)]
			loss = self.loss_func(logit_sampled)
			losses.append(loss.item())
			loss.backward()
			self.optim.step()

		mean_losses = np.mean(losses)
		return mean_losses