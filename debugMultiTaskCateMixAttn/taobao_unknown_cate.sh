CUDA_VISIBLE_DEVICES=1 python main.py --data_folder ../Data/tmall/100000_unknown_cate/ --data_action item.pickle --data_cate cate.pickle --data_time time.pickle --data_name taobao --embedding_dim 300 --hidden_size 300 --lr 0.001 --window_size 5 --test_observed 5 --n_epochs 300 --shared_embedding 1 --batch_size 200 --optimizer_type Adam 