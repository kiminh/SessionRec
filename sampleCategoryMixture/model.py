from torch import nn
import torch
import torch.nn.functional as F
import numpy as np
from torch.nn.utils.rnn import pad_sequence

class GRU4REC(nn.Module):
    def __init__(self, log, ss, window_size, input_size, hidden_size, output_size, embedding_dim, cate_input_size, cate_output_size, cate_embedding_dim, cate_hidden_size, num_layers=1, final_act='tanh', dropout_hidden=.8, dropout_input=0, batch_size=50, use_cuda=False, shared_embedding=True, cate_shared_embedding=True):
        super(GRU4REC, self).__init__()
        self.m_log = log
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.num_layers = num_layers
        self.dropout_hidden = dropout_hidden
        self.dropout_input = dropout_input
        self.embedding_dim = embedding_dim
        self.batch_size = batch_size
        self.use_cuda = use_cuda
        self.window_size = window_size
        self.device = torch.device('cuda' if use_cuda else 'cpu')
        self.m_cate_input_size = cate_input_size
        self.m_cate_embedding_dim = cate_embedding_dim
        self.m_cate_hidden_size = cate_hidden_size
        self.m_cate_output_size = cate_output_size
        # self.h2o = nn.Linear(hidden_size, output_size)

        self.m_cate_embedding = nn.Embedding(self.m_cate_input_size, self.m_cate_embedding_dim)
        self.m_cate_gru = nn.GRU(self.m_cate_embedding_dim, self.m_cate_hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)
        self.m_cate_h2o = nn.Linear(self.m_cate_hidden_size, self.m_cate_output_size)

        # self.create_final_activation(final_act)

        self.look_up = nn.Embedding(input_size, self.embedding_dim)
        self.m_cate_session_gru = nn.GRU(self.embedding_dim, self.hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)
        self.m_short_gru = nn.GRU(self.embedding_dim, self.hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)
        self.fc = nn.Linear(hidden_size*2, hidden_size)
        self.m_ss = ss

        if shared_embedding:
            message = "share embedding"
            self.m_log.addOutput2IO(message)

            self.m_ss.params.weight = self.look_up.weight

        if cate_shared_embedding:
            message = "cate prediction share embedding"
            self.m_log.addOutput2IO(message)

            self.m_cate_h2o.weight = self.m_cate_embedding.weight
            # self.h2o.weight.data = self.look_up.weight.data
           
        self = self.to(self.device)

    def create_final_activation(self, final_act):
        if final_act == 'tanh':
            self.final_activation = nn.Tanh()
        elif final_act == 'relu':
            self.final_activation = nn.ReLU()
        elif final_act == 'softmax':
            self.final_activation = nn.Softmax()
        elif final_act == 'softmax_logit':
            self.final_activation = nn.LogSoftmax()
        elif final_act.startswith('elu-'):
            self.final_activation = nn.ELU(alpha=float(final_act.split('-')[1]))
        elif final_act.startswith('leaky-'):
            self.final_activation = nn.LeakyReLU(negative_slope=float(final_act.split('-')[1]))

    """
    cate_subseq_batch: [cate_index for each subsequence in a batch]
    cate_batch: [cate_index for latest 5 actions]
    """

    def forward(self, input_cate_batch, cate_subseq_batch, mask_cate_batch, mask_cate_seq_batch, max_actionNum_cate_batch, max_subseqNum_cate_batch, subseqLen_cate_batch, seqLen_cate_batch, input_batch, mask_batch, seqLen_batch, cate_batch, train_test_flag):

        embedded_cate = input_cate_batch
        embedded_cate = self.look_up(embedded_cate)

        batch_size_cate = embedded_cate.size(0)
        hidden_subseq_cate = self.init_hidden(batch_size_cate, self.hidden_size)

        ### embedded: batch_size*seq_len*hidden_size
        output_subseq_cate, hidden_subseq_cate = self.m_cate_session_gru(embedded_cate, hidden_subseq_cate) # (sequence, B, H)

        mask_cate_batch = mask_cate_batch.unsqueeze(-1)
       
        output_subseq_cate = output_subseq_cate*mask_cate_batch
        
        # pad_subseqLen_cate_batch = np.array([i-1 if i > 0 else 0 for i in subseqLen_cate_batch])
        first_dim_index = torch.arange(batch_size_cate).to(self.device)
        second_dim_index = torch.from_numpy(subseqLen_cate_batch).to(self.device)
        
        input_seq_cate = output_subseq_cate[first_dim_index, second_dim_index, :]

        ### batch_size_seq*seq_len*hidden_size
        input_seq_cate = input_seq_cate.reshape(-1, max_subseqNum_cate_batch, output_subseq_cate.size(-1))
        input_seq_cate = input_seq_cate.contiguous()
        
        #####################
        ### get the output from 5 latest actions
        embedded_short = input_batch
        embedded_short = self.look_up(embedded_short)

        batch_size_short = embedded_short.size(0)
        hidden_subseq_shrot = self.init_hidden(batch_size_short, self.hidden_size)

        output_subseq_short, hidden_subseq_shrot = self.m_short_gru(embedded_short, hidden_subseq_shrot)

        mask_short_batch = mask_batch.unsqueeze(-1).float()
        output_subseq_short = output_subseq_short*mask_short_batch

        # pad_seqLen_batch = [i-1 if i > 0 else 0 for i in seqLen_batch]
        first_dim_index = torch.arange(batch_size_short).to(self.device)
        second_dim_index = torch.from_numpy(seqLen_batch).to(self.device)

        ### batch_size*hidden_size
        output_short = output_subseq_short[first_dim_index, second_dim_index, :]
        # output_seq, hidden_seq = self.m_short_gru(input_seq, hidden_seq)

        ########
        ####get output from 5 latest actions of cate

        cate_embedded = self.m_cate_embedding(cate_batch)
        batch_size_short = cate_embedded.size(0)
        cate_hidden = self.init_hidden(batch_size_short, self.m_cate_hidden_size)
        cate_output, cate_hidden = self.m_cate_gru(cate_embedded, cate_hidden)

        cate_output_mask = cate_output*mask_short_batch
        cate_last_output_mask = cate_output_mask[first_dim_index, second_dim_index, :]
        
        ### logit_cate_mask: category prediction
        cate_logit_mask = self.m_cate_h2o(cate_last_output_mask)
        # cate_prob_mask = F.softmax(cate_logit_mask, dim=-1)

        # if train_test_flag == "test":
        #     print("cate_subseq_batch", cate_subseq_batch)

        # first_dim_index = torch.arange(batch_size_short).to(self.device).reshape(-1, 1)
        # second_dim_index = torch.from_numpy(cate_subseq_batch).to(self.device)

        ### weight_normalized: batch_size*subseq_num
        # weight_normalized = cate_prob_mask[first_dim_index, second_dim_index]

        # ### weight_normalized: batch_size*subseq_num
        # weight_normalized_mask = weight_normalized*mask_cate_seq_batch

        # weight_normalized_mask_sum = torch.sum(weight_normalized_mask, dim=1)
        # weight_normalized_mask_sum = weight_normalized_mask_sum.unsqueeze(-1)
        # weight_normalized_mask = weight_normalized_mask/weight_normalized_mask_sum

        # weight_normalized_mask = weight_normalized_mask.unsqueeze(-1)
        # weighted_input_seq_cate = weight_normalized_mask*input_seq_cate
      
        # sum_input_seq_cate = torch.sum(weighted_input_seq_cate, dim=1)

        avg_input_seq_cate = input_seq_cate.permute(0, 2, 1)
        sum_input_seq_cate = F.avg_pool1d(avg_input_seq_cate, avg_input_seq_cate.size(-1))
    
        sum_input_seq_cate = sum_input_seq_cate.squeeze()
        output_short = output_short.squeeze()

        mixture_output = torch.cat((sum_input_seq_cate, output_short), dim=1)
        fc_output = self.fc(mixture_output)
        # mixture_output = sum_input_seq_cate+output_short

        # logits, new_targets = self.m_ss(fc_output, target_y_batch)
        # return output_short, cate_logit_mask
        return fc_output, cate_logit_mask

    def embedding_dropout(self, input):
        p_drop = torch.Tensor(input.size(0), input.size(1), 1).fill_(1 - self.dropout_input)  # (B,1)
        mask = torch.bernoulli(p_drop).expand_as(input) / (1 - self.dropout_input)  # (B,C)
        mask = mask.to(self.device)
        input = input * mask  # (B,C)

        return input

    def init_hidden(self, batch_size, hidden_size):
        '''
        Initialize the hidden state of the GRU
        '''
        h0 = torch.zeros(self.num_layers, batch_size, hidden_size).to(self.device)
        return h0