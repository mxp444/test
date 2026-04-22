"""
用这个
"""

import numpy as np
from keras.models import Model
from keras.layers import Dense, Dropout
from keras.applications.mobilenet import MobileNet
from keras.applications.mobilenet import preprocess_input
from keras.preprocessing.image import load_img, img_to_array
import tensorflow as tf
from utils.score_utils import mean_score, std_score

class design_sense():
    def __init__(self):
        with tf.device('/CPU:0'):
            self.base_model = MobileNet((None, None, 3), alpha=1, include_top=False, pooling='avg', weights=None)
            self.x = Dropout(0.75)(self.base_model.output)
            self.x = Dense(10, activation='softmax')(self.x)
            self.model = Model(self.base_model.input, self.x)
            self.model.load_weights('weights/mobilenet_weights.h5')

    def predict(self, imgs):
        score_list = []
        for img_path in imgs:
            img = load_img(img_path, target_size=None)
            x = img_to_array(img)
            x = np.expand_dims(x, axis=0)
            x = preprocess_input(x)
            scores = self.model.predict(x, batch_size=1, verbose=0)[0]
            mean = mean_score(scores)
            std = std_score(scores)
            score_list.append((mean, std))

        return score_list[0]


if __name__ == "__main__":
    imgs = ["images/NIMA.jpg"]
    model = design_sense()
    mean, std = model.predict(imgs)
    print("NIMA Score : %0.3f +- (%0.3f)" % (mean, std))

    """
    得分中位数，上下浮动
    """




