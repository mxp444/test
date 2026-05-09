"""
用这个
"""

import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from keras.models import Model
from keras.layers import Dense, Dropout
from keras.applications.mobilenet import MobileNet
from keras.applications.mobilenet import preprocess_input
from keras.preprocessing.image import load_img, img_to_array
import tensorflow as tf
from utils.score_utils import mean_score, std_score

class Design_sense():
    def __init__(self):
        weights_path = Path(__file__).resolve().parent / "weights" / "mobilenet_weights.h5"
        if not weights_path.exists():
            raise FileNotFoundError(f"设计感模型权重不存在: {weights_path}")
        with tf.device('/CPU:0'):
            self.base_model = MobileNet((None, None, 3), alpha=1, include_top=False, pooling='avg', weights=None)
            self.x = Dropout(0.75)(self.base_model.output)
            self.x = Dense(10, activation='softmax')(self.x)
            self.model = Model(self.base_model.input, self.x)
            self.model.load_weights(str(weights_path))

    def predict(self, img_path):
        img = load_img(img_path, target_size=None)
        x = img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        scores = self.model.predict(x, batch_size=1, verbose=0)[0]
        mean = mean_score(scores)
        std = std_score(scores)


        return mean, std


if __name__ == "__main__":
    imgs = r"C:\Users\R9000P\Desktop\毕设\整合\pics\490f705bd73faaa6711001ea4ae5de15.jpeg"
    model = Design_sense()
    mean, std = model.predict(imgs)
    print("NIMA Score : %0.3f +- (%0.3f)" % (mean, std))

    """
    得分中位数，上下浮动
    """




