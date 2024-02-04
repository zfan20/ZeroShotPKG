# -*- coding: utf-8 -*-

import os
import numpy as np
import random
import torch
import pickle
import argparse

from torch.utils.data import DataLoader, RandomSampler, SequentialSampler

from datasets import SASRecDataset
from trainers import FinetuneTrainer, DistSAModelTrainer, HeteroGNNPretrainer
from models import S3RecModel
from seqmodels import SASRecModel, DistSAModel, DistMeanSAModel
from utils import EarlyStopping, get_user_seqs, get_item2attribute_json, check_path, set_seed, get_hetero_dglgraph

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--data_dir', default='../preprocess_data/', type=str)
    parser.add_argument('--output_dir', default='output/', type=str)
    parser.add_argument('--data_name', default='Beauty', type=str)
    parser.add_argument('--market', default='uk', type=str)
    parser.add_argument('--do_eval', action='store_true')
    parser.add_argument('--ckp', default=10, type=int, help="pretrain epochs 10, 20, 30...")

    # model args
    parser.add_argument("--model_name", default='Finetune_full', type=str)
    parser.add_argument("--hidden_size", type=int, default=64, help="hidden size of transformer model")
    parser.add_argument("--num_hidden_layers", type=int, default=2, help="number of layers")
    parser.add_argument('--num_attention_heads', default=2, type=int)
    parser.add_argument('--hidden_act', default="gelu", type=str) # gelu relu
    parser.add_argument("--attention_probs_dropout_prob", type=float, default=0.5, help="attention dropout p")
    parser.add_argument("--hidden_dropout_prob", type=float, default=0.5, help="hidden dropout p")
    parser.add_argument("--initializer_range", type=float, default=0.02)
    parser.add_argument('--max_seq_length', default=50, type=int)
    parser.add_argument('--distance_metric', default='wasserstein', type=str)
    parser.add_argument('--pvn_weight', default=0.1, type=float)
    parser.add_argument('--kernel_param', default=1.0, type=float)

    # train args
    parser.add_argument("--lr", type=float, default=0.001, help="learning rate of adam")
    parser.add_argument("--batch_size", type=int, default=256, help="number of batch_size")
    parser.add_argument("--epochs", type=int, default=300, help="number of epochs")
    parser.add_argument("--no_cuda", action="store_true")
    parser.add_argument("--log_freq", type=int, default=1, help="per epoch print res")
    parser.add_argument("--seed", default=42, type=int)

    parser.add_argument("--weight_decay", type=float, default=0.0, help="weight_decay of adam")
    parser.add_argument("--adam_beta1", type=float, default=0.9, help="adam first beta value")
    parser.add_argument("--adam_beta2", type=float, default=0.999, help="adam second beta value")
    parser.add_argument("--gpu_id", type=str, default="0", help="gpu_id")

    args = parser.parse_args()

    set_seed(args.seed)
    check_path(args.output_dir)


    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id
    args.cuda_condition = torch.cuda.is_available() and not args.no_cuda

    args.data_file = args.data_dir + args.data_name + '/seqs_{}.txt'.format(args.market)
    #item2attribute_file = args.data_dir + args.data_name + '_item2attributes.json'

    pkg_file = args.data_dir + args.data_name + '/indexed_edges.txt'

    user_seq, max_item, valid_rating_matrix, test_rating_matrix, num_users = \
        get_user_seqs(args.data_file)

    pkg_graph = get_hetero_dglgraph(pkg_file)

    #item2attribute, attribute_size = get_item2attribute_json(item2attribute_file)

    args.item_size = max_item + 2
    args.num_users = num_users
    args.mask_id = max_item + 1
    #args.attribute_size = attribute_size + 1

    # save model args
    args_str = f'{args.model_name}-{args.data_name}-{args.hidden_size}-{args.num_hidden_layers}-{args.num_attention_heads}-{args.hidden_act}-{args.attention_probs_dropout_prob}-{args.hidden_dropout_prob}-{args.max_seq_length}-{args.lr}-{args.weight_decay}-{args.ckp}-{args.kernel_param}-{args.pvn_weight}-{args.market}'
    args.log_file = os.path.join(args.output_dir, args_str + '.txt')
    print(str(args))
    with open(args.log_file, 'a') as f:
        f.write(str(args) + '\n')

    #args.item2attribute = item2attribute
    # set item score in train set to `0` in validation
    args.train_matrix = valid_rating_matrix

    # save model
    checkpoint = args_str + '.pt'
    args.checkpoint_path = os.path.join(args.output_dir, checkpoint)

    # save pkg model
    args.pkg_ckp_path = os.path.join(args.output_dir, args_str+'pkg_model.pt')

    # save pkg item embs
    args.pkg_items_embs_path = os.path.join(args.output_dir, args_str+'pkg_item_embs.npy')

    if 'pretrain_pkg' not in args.model_name:
        train_dataset = SASRecDataset(args, user_seq, data_type='train')
        train_sampler = RandomSampler(train_dataset)
        train_dataloader = DataLoader(train_dataset, sampler=train_sampler, batch_size=args.batch_size)

        eval_dataset = SASRecDataset(args, user_seq, data_type='valid')
        eval_sampler = SequentialSampler(eval_dataset)
        #eval_dataloader = DataLoader(eval_dataset, sampler=eval_sampler, batch_size=200)

        test_dataset = SASRecDataset(args, user_seq, data_type='test')
        test_sampler = SequentialSampler(test_dataset)
        #test_dataloader = DataLoader(test_dataset, sampler=test_sampler, batch_size=200)


    if args.model_name == 'DistSAModel':
        model = DistSAModel(args=args)
        eval_dataloader = DataLoader(eval_dataset, sampler=eval_sampler, batch_size=100)
        test_dataloader = DataLoader(test_dataset, sampler=test_sampler, batch_size=100)
        trainer = DistSAModelTrainer(model, train_dataloader, eval_dataloader,
                                    test_dataloader, args)
    elif args.model_name == 'DistMeanSAModel':
        model = DistMeanSAModel(args=args)
        eval_dataloader = DataLoader(eval_dataset, sampler=eval_sampler, batch_size=100)
        test_dataloader = DataLoader(test_dataset, sampler=test_sampler, batch_size=100)
        trainer = DistSAModelTrainer(model, train_dataloader, eval_dataloader,
                                    test_dataloader, args)
    elif args.model_name == 'SASRec':
        model = SASRecModel(args=args)
        eval_dataloader = DataLoader(eval_dataset, sampler=eval_sampler, batch_size=args.batch_size)
        test_dataloader = DataLoader(test_dataset, sampler=test_sampler, batch_size=args.batch_size)

        trainer = FinetuneTrainer(model, train_dataloader, eval_dataloader,
                                test_dataloader, args)

    elif args.model_name == 'pretrain_pkg_RGCN':
        trainer = HeteroGNNPretrainer(pkg_graph, args)


    if args.do_eval:
        trainer.load(args.checkpoint_path)
        print(f'Load model from {args.checkpoint_path} for test!')
        #scores, result_info, _ = trainer.test(0, full_sort=True)
        trainer.args.train_matrix = test_rating_matrix
        #scores, result_info, _ = trainer.complicated_eval(user_seq, args)
        scores, result_info, pred_details = trainer.eval_visualization(user_seq, args)
        with open('./'+ args_str + '_best_preds.pkl', 'wb') as f:
            pickle.dump(pred_details, f, pickle.HIGHEST_PROTOCOL)

    else:
        #pretrained_path = os.path.join(args.output_dir, f'{args.data_name}-epochs-{args.ckp}.pt')
        #try:
        #    trainer.load(pretrained_path)
        #    print(f'Load Checkpoint From {pretrained_path}!')

        #except FileNotFoundError:
        #    print(f'{pretrained_path} Not Found! The Model is same as SASRec')
       
        if 'pretrain_pkg' not in args.model_name:
            if args.model_name == 'DistSAModel':
                early_stopping = EarlyStopping(args.checkpoint_path, patience=100, verbose=True)
            else:
                early_stopping = EarlyStopping(args.checkpoint_path, patience=50, verbose=True)
            for epoch in range(args.epochs):
                trainer.train(epoch)
                # evaluate on MRR
                scores, _, _ = trainer.valid(epoch, full_sort=True)
                early_stopping(np.array(scores[-1:]), trainer.model)
                if early_stopping.early_stop:
                    print("Early stopping")
                    break

            print('---------------Change to test_rating_matrix!-------------------')
            # load the best model
            trainer.model.load_state_dict(torch.load(args.checkpoint_path))
            valid_scores, _, _ = trainer.valid('best', full_sort=True)
            trainer.args.train_matrix = test_rating_matrix
            scores, result_info, _ = trainer.test('best', full_sort=True)
        else:
            trainer.train()
            trainer.save_item_embs(args.pkg_items_embs_path)
            trainer.save(args.pkg_ckp_path)

    print(args_str)
    #print(result_info)
    with open(args.log_file, 'a') as f:
        f.write(args_str + '\n')
        f.write(result_info + '\n')
main()
