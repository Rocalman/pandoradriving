# pandoradriving

## Requirements

* **Tensorflow 1.2.0**
* Python 2.7
* CUDA 8.0+ (For GPU)
* Python Libraries: numpy, scipy, matplotlib， opencv-python

## Quick Start
### Training
    python train.py --model pilotnet_io_lstm --batch_size 16 --max_epoch 300 --gpu 0 --log_dir logs_pilot --loss_function mae
The loss function includes mae， mse, stlossmse, stlosss2

To see HELP for the training script:

    python train.py -h

### Evaluation
    python eval.py --model pilotnet_io_lstm --batch_size 16 --gpu 1 --model_path logs_pilot/pilotnet_io_lstm/model_best.ckpt --result_dir result --loss_function mae

### Prediction
    python predict.py --model pilotnet_io_lstm --model_path logs_pilot/pilotnet_io_lstm/model_best.ckpt --result_dir result_predict --loss_function mae --add_orientations False
