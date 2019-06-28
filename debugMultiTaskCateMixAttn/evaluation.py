import numpy as np
import torch
import dataset
from metric import *

class Evaluation(object):
	def __init__(self, log, model, loss_func, use_cuda, k=20, warm_start=5):
		self.model = model
		self.loss_func = loss_func

		self.topk = k
		self.warm_start = warm_start
		self.device = torch.device('cuda' if use_cuda else 'cpu')
		self.m_log = log

	def eval(self, eval_data, batch_size):
		self.model.eval()

		losses = []
		recalls = []
		mrrs = []
		weights = []

		target_item_losses = []
		target_cate_losses = []
		input_cate_losses = []

		# losses = None
		# recalls = None
		# mrrs = None

		dataloader = eval_data

		eval_iter = 0

		with torch.no_grad():
			total_test_num = []

			for x_cate_batch, mask_cate, mask_cate_seq, max_acticonNum_cate, max_subseqNum_cate, subseqLen_cate, seqLen_cate, cate_subseq, target_cate, x_batch, mask_batch, seqLen_batch, y_batch, idx_batch in dataloader:
			# for x_cate_batch, mask_cate, mask_cate_seq, max_acticonNum_cate, max_subseqNum_cate, subseqLen_cate, seqLen_cate, x_batch, mask_batch, seqLen_batch, y_batch, idx_batch in dataloader:

				x_cate_batch = x_cate_batch.to(self.device)
				mask_cate = mask_cate.to(self.device)
				mask_cate_seq = mask_cate_seq.to(self.device)
				
				x_batch = x_batch.to(self.device)
				mask_batch = mask_batch.to(self.device)

				y_batch = y_batch.to(self.device)
				warm_start_mask = (idx_batch>=self.warm_start).to(self.device)

				cate_subseq = cate_subseq.to(self.device)
				target_cate = target_cate.to(self.device)
				
				# hidden = self.model.init_hidden()

				logit_batch, output_cate_subseq, output_cate = self.model(x_cate_batch, mask_cate, mask_cate_seq, max_acticonNum_cate, max_subseqNum_cate, subseqLen_cate, seqLen_cate, x_batch, mask_batch, seqLen_batch, "test")
				# logit_batch = self.model(x_cate_batch, mask_cate, mask_cate_seq, max_acticonNum_cate, max_subseqNum_cate, subseqLen_cate, seqLen_cate, x_batch, mask_batch, seqLen_batch, "test")
				
				logit_sampled_batch = logit_batch[:, y_batch.view(-1)]
				loss_batch = self.loss_func(logit_sampled_batch, y_batch)

				output_cate_subseq_sampled = output_cate_subseq[:, cate_subseq.view(-1)]
				loss_cate_subseq_batch = self.loss_func(output_cate_subseq_sampled, cate_subseq)
				
				output_cate_sampled = output_cate[:, target_cate.view(-1)]
				loss_cate_batch = self.loss_func(output_cate_sampled, target_cate)
				
				# multi_loss = loss_batch
				multi_loss = loss_batch+loss_cate_subseq_batch+loss_cate_batch

				target_item_losses.append(loss_batch.item())
				target_cate_losses.append(loss_cate_batch.item())
				input_cate_losses.append(loss_cate_subseq_batch)

				losses.append(multi_loss.item())
				
				recall_batch, mrr_batch = evaluate(logit_batch, y_batch, warm_start_mask, k=self.topk)

				weights.append( int( warm_start_mask.int().sum() ) )
				recalls.append(recall_batch)
				mrrs.append(mrr_batch)

				total_test_num.append(y_batch.view(-1).size(0))

		mean_losses = np.mean(losses)
		mean_target_item_losses = np.mean(target_item_losses)
		mean_target_cate_losses = np.mean(target_cate_losses)
		mean_input_cate_losses = np.mean(input_cate_losses)

		mean_recall = np.average(recalls, weights=weights)
		mean_mrr = np.average(mrrs, weights=weights)

		msg = "total_test_num"+str(np.sum(total_test_num))
		self.m_log.addOutput2IO(msg)

		return mean_losses, mean_target_item_losses, mean_target_cate_losses, mean_input_cate_losses,  mean_recall, mean_mrr