from torch import nn
import torch
import torch.nn.functional as F
import numpy as np
from torch.nn.utils.rnn import pad_sequence

class GRU4REC(nn.Module):
    def __init__(self, window_size, input_size, hidden_size, output_size, num_layers=1, final_act='tanh', dropout_hidden=.8, dropout_input=0, batch_size=50, embedding_dim=-1, use_cuda=False, shared_embedding=True):
        super(GRU4REC, self).__init__()
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
        
        self.h2o = nn.Linear(hidden_size, output_size)
            
        self.create_final_activation(final_act)

        self.look_up = nn.Embedding(input_size, self.embedding_dim).to(self.device)
        self.m_cate_gru = nn.GRU(self.embedding_dim, self.hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)
        self.m_short_gru = nn.GRU(self.embedding_dim, self.hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)

        self.m_mix_gru = nn.GRU(self.hidden_size, self.hidden_size, self.num_layers, dropout=self.dropout_hidden, batch_first=True)

        if shared_embedding:
            print("share embedding")
            self.out_matrix = self.look_up.weight.to(self.device)
        else:
            print("separate embedding")
            self.out_matrix = torch.rand(output_size, hidden_size, requires_grad=True).to(self.device)

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

    def forward(self, input_cate_batch, mask_cate_batch, max_actionNum_cate_batch, max_subseqNum_cate_batch, subseqLen_cate_batch, seqLen_cate_batch, input_batch, mask_batch, seqLen_batch, train_test_flag):

        embedded_cate = input_cate_batch
        embedded_cate = self.look_up(embedded_cate)

        batch_size_cate = embedded_cate.size(0)
        hidden_subseq_cate = self.init_hidden(batch_size_cate)

        ### embedded: batch_size*seq_len*hidden_size
        output_subseq_cate, hidden_subseq_cate = self.m_cate_gru(embedded_cate, hidden_subseq_cate) # (sequence, B, H)

        mask_cate_batch = mask_cate_batch.unsqueeze(-1)
       
        output_subseq_cate = output_subseq_cate*mask_cate_batch
        
        pad_subseqLen_cate_batch = [i-1 if i > 0 else 0 for i in subseqLen_cate_batch]
        first_dim_index = torch.arange(batch_size_cate).to(self.device)
        second_dim_index = torch.LongTensor(pad_subseqLen_cate_batch).to(self.device)
        
        input_seq_cate = output_subseq_cate[first_dim_index, second_dim_index, :]

        ### batch_size_seq*seq_len*hidden_size
        input_seq_cate = input_seq_cate.reshape(-1, max_subseqNum_cate_batch, output_subseq_cate.size(-1))
        input_seq_cate = input_seq_cate.contiguous()
        
        ### get the output from 5 latest actions
        embedded_short = input_batch
        embedded_short = self.look_up(embedded_short)

        batch_size_short = embedded_short.size(0)
        hidden_subseq_shrot = self.init_hidden(batch_size_short)

        output_subseq_short, hidden_subseq_shrot = self.m_short_gru(embedded_short, hidden_subseq_shrot)

        mask_short_batch = mask_batch.unsqueeze(-1).float()
        output_subseq_short = output_subseq_short*mask_short_batch

        pad_seqLen_batch = [i-1 if i > 0 else 0 for i in seqLen_batch]
        first_dim_index = torch.arange(batch_size_short).to(self.device)
        second_dim_index = torch.LongTensor(pad_seqLen_batch).to(self.device)

        ### batch_size*hidden_size
        output_short = output_subseq_short[first_dim_index, second_dim_index, :]
        # output_seq, hidden_seq = self.m_short_gru(input_seq, hidden_seq)
       
        output_short = output_short.unsqueeze(-1)

        # print("output_short", output_short.size())
        # print("input_seq_cate size", input_seq_cate.size())
        weight = torch.matmul(input_seq_cate, output_short)
        weight_normalized = F.softmax(weight, dim=1)

        if train_test_flag == "test":
            print("weight", weight_normalized)

        weighted_input_seq_cate = weight_normalized*input_seq_cate

        sum_input_seq_cate = torch.sum(weighted_input_seq_cate, dim=1)
        output_short = output_short.squeeze()

        mixture_output = sum_input_seq_cate+output_short

        ### debug: if output only comes from short
        # mixture_output = output_short
        # print("mixture_output", mixture_output)

        output = F.linear(mixture_output, self.out_matrix)
        
        logit = output

        return logit


    def onehot_encode(self, input):
        """
        Returns a one-hot vector corresponding to the input

        Args:
            input (B,): torch.LongTensor of item indices
            buffer (B,output_size): buffer that stores the one-hot vector
        Returns:
            one_hot (B,C): torch.FloatTensor of one-hot vectors
        """

        self.onehot_buffer.zero_()

        index = input.unsqueeze(2)
        # index = input.view(-1, 1)
        one_hot = self.onehot_buffer.scatter_(2, index, 1)

        return one_hot

    def embedding_dropout(self, input):
        p_drop = torch.Tensor(input.size(0), input.size(1), 1).fill_(1 - self.dropout_input)  # (B,1)
        mask = torch.bernoulli(p_drop).expand_as(input) / (1 - self.dropout_input)  # (B,C)
        mask = mask.to(self.device)
        input = input * mask  # (B,C)

        return input

    def init_hidden(self, batch_size):
        '''
        Initialize the hidden state of the GRU
        '''
        h0 = torch.zeros(self.num_layers, batch_size, self.hidden_size).to(self.device)
        return h0