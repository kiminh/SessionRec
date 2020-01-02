import torch
import torch.nn as nn
# from torch.autograd import Variable
import torch.nn.functional as F


class LossFunction(nn.Module):
    def __init__(self, loss_type='TOP1', c_weights=None, use_cuda=True):
        """ An abstract loss function that can supports custom loss functions compatible with PyTorch."""
        super(LossFunction, self).__init__()
        self.loss_type = loss_type
        self.device = torch.device('cuda' if use_cuda else 'cpu')
    
        if loss_type == 'XE':
            if c_weights is not None:
                c_weights = torch.from_numpy(c_weights).float().to(self.device)
            self._loss_fn = SampledCrossEntropyLoss(c_weights)
        elif loss_type == 'TOP1':
            self._loss_fn = TOP1Loss()
        elif loss_type == 'BPR':
            self._loss_fn = BPRLoss()
        elif loss_type == 'TOP1-max':
            self._loss_fn = TOP1_max()
        elif loss_type == 'BPR-max':
            self._loss_fn = BPR_max()
        else:
            raise NotImplementedError

    def forward(self, logit, target):
        return self._loss_fn(logit, target)

class SampledCrossEntropyLoss(nn.Module):
    """ CrossEntropyLoss with n_classes = batch_size = the number of samples in the session-parallel mini-batch """
    def __init__(self, c_weights):
       
        super(SampledCrossEntropyLoss, self).__init__()
        if c_weights is not None:
            self.xe_loss = nn.CrossEntropyLoss(weight=c_weights)
        else:
            self.xe_loss = nn.CrossEntropyLoss()
        # self.xe_loss = nn.CrossEntropyLoss()

    def forward(self, logit, target):
    
        return self.xe_loss(logit.view(target.size(0), -1), target)


class BPRLoss(nn.Module):
    def __init__(self):
        """
        See Balazs Hihasi(ICLR 2016), pg.5
        """
        super(BPRLoss, self).__init__()

    def forward(self, logit, target):
        """
        Args:
            logit (BxB): Variable that stores the logits for the items in the mini-batch
                         The first dimension corresponds to the batches, and the second
                         dimension corresponds to sampled number of items to evaluate
        """

        # differences between the item scores

        diff = logit.view(-1, 1).expand_as(logit) - logit
        # final loss
        loss = -torch.mean(F.logsigmoid(diff))

        return loss


# class BPR_max(nn.Module):
#     def __init__(self):
#         """
#         See https://arxiv.org/pdf/1706.03847.pdf, formula (12)
#         """
#         super(BPR_max, self).__init__()

#     def forward(self, logit_pos, logit_neg, target):

#         logit_softmax = F.softmax(logit, dim=1)
#         diff = logit.diag().view(-1, 1).expand_as(logit) - logit
#         loss = -torch.log(torch.mean(logit_softmax * torch.sigmoid(diff)))
#         return loss


class TOP1Loss(nn.Module):
    def __init__(self):
        """
        See Balazs Hihasi(ICLR 2016), pg.5
        """
        super(TOP1Loss, self).__init__()

    def forward(self, logit_pos, logit_neg, target):
        """
        Args:
            logit (BxB): Variable that stores the logits for the items in the mini-batch
                         The first dimension corresponds to the batches, and the second
                         dimension corresponds to sampled number of items to evaluate
        """
        # differences between the item scores
        # print("logit size", logit.size())

        # print("logit neg size", logit_neg.size())
        # print("logit pos size", logit_pos.size())

        diff = -(logit_pos.view(-1, 1).expand_as(logit_neg) - logit_neg)
        # final loss
        loss = torch.sigmoid(diff).mean() + torch.sigmoid(logit_neg ** 2).mean()

        return loss


# class TOP1_max(nn.Module):

#     def __init__(self):
#         """
#         See https://arxiv.org/pdf/1706.03847.pdf, formula (9)
#         """
#         super(TOP1_max, self).__init__()

#     def forward(self, logit_pos, logit_neg, target):
#         logit_softmax = F.softmax(logit, dim=1)

#         diff = -(logit.diag().view(-1, 1).expand_as(logit) - logit)
#         loss = torch.mean(logit_softmax * (torch.sigmoid(diff) + torch.sigmoid(logit ** 2)))
#         return loss