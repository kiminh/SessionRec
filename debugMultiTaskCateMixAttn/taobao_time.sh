CUDA_VISIBLE_DEVICES=2 python main_time.py --data_folder ../Data/tmall/100000_cate/ --data_action item_time.pickle --data_cate cate_time.pickle --data_time time_time.pickle --data_name taobao --embedding_dim 300 --hidden_size 300 --lr 0.001 --window_size 5 --test_observed 5 --n_epochs 300 --shared_embedding 1 --batch_size 80 --optimizer_type Adam