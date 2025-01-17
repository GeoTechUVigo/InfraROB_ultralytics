# Code from https://github.com/rooneysh/Labelme2YOLO
# Expects 'label' attribute to have format 'id_cls'
'''
Created on Aug 18, 2021

@author: xiaosonh
'''
import os
import sys
import argparse
import shutil
import math
from collections import OrderedDict

import json
import cv2
import PIL.Image

from sklearn.model_selection import train_test_split
from labelme import utils


class Labelme2YOLO(object):

    def __init__(self, json_dir, **kwargs):
        self._json_dir = json_dir
        self._target_dir = kwargs["args"].target_dir
        self._multi_video = kwargs["args"].multi_video
        self._split_dataset = kwargs["args"].split_dataset
        self._save_image = kwargs["args"].save_image
        self._shift_class_id = kwargs["args"].shift_class_id
        if not self._save_image:
            self._image_width = kwargs["args"].image_width
            self._image_height = kwargs["args"].image_height

        self._label_id_map = self._get_label_id_map(self._json_dir)

    def _make_train_val_dir(self):
        if self._target_dir:
            self._label_dir_path = os.path.join(self._json_dir, 
                                                'YOLODataset/labels/')
            self._image_dir_path = os.path.join(self._json_dir, 
                                                'YOLODataset/images/')
        else:
            self._label_dir_path = self._target_dir
            self._image_dir_path = self._target_dir

        for yolo_path in (os.path.join(self._label_dir_path + 'train/'), 
                          os.path.join(self._label_dir_path + 'val/'),
                          os.path.join(self._image_dir_path + 'train/'), 
                          os.path.join(self._image_dir_path + 'val/')):
            if not self._multi_video:
                shutil.rmtree(yolo_path)
            if not os.path.exists(yolo_path):
                os.makedirs(yolo_path)

    def _make_not_split_dir(self):
        if self._target_dir is None:
            self._label_dir_path = os.path.join(self._json_dir, 
                                                'YOLODataset/labels/')
            self._image_dir_path = os.path.join(self._json_dir, 
                                                'YOLODataset/images/')
        else:
            self._label_dir_path = self._target_dir
            self._image_dir_path = self._target_dir

        for yolo_path in (self._label_dir_path,
                          self._image_dir_path):
            if not self._multi_video:
                shutil.rmtree(yolo_path)
            if not os.path.exists(yolo_path):
                os.makedirs(yolo_path)

    def _get_label_id_map(self, json_dir):
        label_set = set()

        for path, _, files in os.walk(json_dir):
            for file_name in files:
                if file_name.endswith('json'):
                    json_path = os.path.join(path, file_name)
                    try:
                        data = json.load(open(json_path))
                    except:
                        continue
                    for shape in data['shapes']:
                        if not '_' in shape['label']:
                            continue
                        label_set.add(shape['label'])

        dict = OrderedDict([label.split('_') for label in label_set])
        dict = OrderedDict([(k, str(int(v) + self._shift_class_id)) for k, v in dict.items()])

        return dict

    def _train_test_split(self, folders, json_names, val_size):
        if len(folders) > 0 and 'train' in folders and 'val' in folders:
            train_folder = os.path.join(self._json_dir, 'train/')
            train_json_names = [train_sample_name + '.json' \
                                for train_sample_name in os.listdir(train_folder) \
                                if os.path.isdir(os.path.join(train_folder, train_sample_name))]

            val_folder = os.path.join(self._json_dir, 'val/')
            val_json_names = [val_sample_name + '.json' \
                              for val_sample_name in os.listdir(val_folder) \
                              if os.path.isdir(os.path.join(val_folder, val_sample_name))]

            return train_json_names, val_json_names

        train_idxs, val_idxs = train_test_split(range(len(json_names)), 
                                                test_size=val_size)
        train_json_names = [json_names[train_idx] for train_idx in train_idxs]
        val_json_names = [json_names[val_idx] for val_idx in val_idxs]

        return train_json_names, val_json_names

    def convert(self, val_size):
        json_names = [file_name for file_name in os.listdir(self._json_dir) \
                      if os.path.isfile(os.path.join(self._json_dir, file_name)) and \
                      file_name.endswith('.json')]
        folders =  [file_name for file_name in os.listdir(self._json_dir) \
                    if os.path.isdir(os.path.join(self._json_dir, file_name))]

        if self._split_dataset:
            train_json_names, val_json_names = self._train_test_split(folders, json_names, val_size)
            self._make_train_val_dir()
        else:
            train_json_names = json_names
            val_json_names = []
            self._make_not_split_dir()

        # convert labelme object to yolo format object, and save them to files
        # also get image from labelme json file and save them under images folder
        for target_dir, json_names in zip(('train/', 'val/'), 
                                          (train_json_names, val_json_names)):
            if not self._split_dataset:
                target_dir = ''
            for json_name in json_names:
                json_path = os.path.join(self._json_dir, json_name)
                json_data = json.load(open(json_path))

                print('Converting %s for %s ...' % (json_name, target_dir.replace('/', '')))

                img_path = self._save_yolo_image(json_data, 
                                                 json_name, 
                                                 self._image_dir_path, 
                                                 target_dir)

                yolo_obj_list = self._get_yolo_object_list(json_data, img_path)
                self._save_yolo_label(json_name, 
                                      self._label_dir_path, 
                                      target_dir, 
                                      yolo_obj_list)

        if self._target_dir is None:
            print('Generating dataset.yaml file ...')
            self._save_dataset_yaml()

    def convert_one(self, json_name):
        json_path = os.path.join(self._json_dir, json_name)
        json_data = json.load(open(json_path))

        print('Converting %s ...' % json_name)

        img_path = self._save_yolo_image(json_data, json_name, 
                                         self._json_dir, '')

        yolo_obj_list = self._get_yolo_object_list(json_data, img_path)
        self._save_yolo_label(json_name, self._json_dir, 
                              '', yolo_obj_list)

    def _get_yolo_object_list(self, json_data, img_path):
        yolo_obj_list = []
        
        if self._save_image:
            img_h, img_w, _ = cv2.imread(img_path).shape
        else:
            img_h = self._image_height
            img_w = self._image_width
        for shape in json_data['shapes']:
            if not '_' in shape['label']:
                continue
            # labelme circle shape is different from others
            # it only has 2 points, 1st is circle center, 2nd is drag end point
            if shape['shape_type'] == 'circle':
                yolo_obj = self._get_circle_shape_yolo_object(shape, img_h, img_w)
            else:
                yolo_obj = self._get_other_shape_yolo_object(shape, img_h, img_w)

            yolo_obj_list.append(yolo_obj)

        return yolo_obj_list

    def _get_circle_shape_yolo_object(self, shape, img_h, img_w):
        obj_center_x, obj_center_y = shape['points'][0]

        radius = math.sqrt((obj_center_x - shape['points'][1][0]) ** 2 + 
                           (obj_center_y - shape['points'][1][1]) ** 2)
        obj_w = 2 * radius
        obj_h = 2 * radius

        yolo_center_x= round(float(obj_center_x / img_w), 6)
        yolo_center_y = round(float(obj_center_y / img_h), 6)
        yolo_w = round(float(obj_w / img_w), 6)
        yolo_h = round(float(obj_h / img_h), 6)

        label_id = self._label_id_map[shape['label'].rsplit('_', 1)[0]]

        return label_id, yolo_center_x, yolo_center_y, yolo_w, yolo_h

    def _get_other_shape_yolo_object(self, shape, img_h, img_w):
        def __get_object_desc(obj_port_list):
            __get_dist = lambda int_list: max(int_list) - min(int_list)

            x_lists = [port[0] for port in obj_port_list]        
            y_lists = [port[1] for port in obj_port_list]

            return min(x_lists), __get_dist(x_lists), min(y_lists), __get_dist(y_lists)

        obj_x_min, obj_w, obj_y_min, obj_h = __get_object_desc(shape['points'])

        yolo_center_x= round(float((obj_x_min + obj_w / 2.0) / img_w), 6)
        yolo_center_y = round(float((obj_y_min + obj_h / 2.0) / img_h), 6)
        yolo_w = round(float(obj_w / img_w), 6)
        yolo_h = round(float(obj_h / img_h), 6)

        label_id = self._label_id_map[shape['label'].rsplit('_', 1)[0]]

        return label_id, yolo_center_x, yolo_center_y, yolo_w, yolo_h

    def _save_yolo_label(self, json_name, label_dir_path, target_dir, yolo_obj_list):
        txt_path = os.path.join(label_dir_path, 
                                target_dir, 
                                json_name.replace('.json', '.txt'))

        with open(txt_path, 'w+') as f:
            for yolo_obj_idx, yolo_obj in enumerate(yolo_obj_list):
                yolo_obj_line = '%s %s %s %s %s\n' % yolo_obj \
                    if yolo_obj_idx + 1 != len(yolo_obj_list) else \
                    '%s %s %s %s %s' % yolo_obj
                f.write(yolo_obj_line)

    def _save_yolo_image(self, json_data, json_name, image_dir_path, target_dir):
        if not self._save_image:
            return ''

        img_name = json_name.replace('.json', '.png')
        img_path = os.path.join(image_dir_path, target_dir,img_name)

        if not os.path.exists(img_path):
            img = utils.img_b64_to_arr(json_data['imageData'])
            PIL.Image.fromarray(img).save(img_path)
        
        return img_path

    def _save_dataset_yaml(self):
        yaml_path = os.path.join(self._json_dir, 'YOLODataset/', 'dataset.yaml')
        
        with open(yaml_path, 'w+') as yaml_file:
            yaml_file.write('train: %s\n' % \
                            os.path.join(self._image_dir_path, 'train/'))
            yaml_file.write('val: %s\n\n' % \
                            os.path.join(self._image_dir_path, 'val/'))
            classes = set(self._label_id_map.values())
            yaml_file.write('nc: %i\n\n' % len(classes))
            
            names_str = ''
            for label, _ in self._label_id_map.items():
                names_str += "'%s', " % label
            names_str = names_str.rstrip(', ')

            names_str = ''
            for cls in classes:
                names_str += "'%s', " % cls
            names_str = names_str.rstrip(', ')

            yaml_file.write('names: [%s]' % names_str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels_dir', type=str,
                        help='Please input the path of the labelme json files')
    parser.add_argument('--target_dir', help='A directory where to save all mixed data',
                        required=False, default=None)
    parser.add_argument('--val_size', type=float, nargs='?', default=None,
                        help='Please input the validation dataset size, for example 0.1')
    parser.add_argument('--json_name', type=str, nargs='?', default=None,
                        help='If you put json name, it would convert only one json file to YOLO.')
    parser.add_argument('--multi_video', default=False, action="store_true",
                        help='If there are multiple videos in subdirectories')
    parser.add_argument('--split_dataset', default=False, action="store_true",
                        help='Split in a stratified train/val dataset')
    parser.add_argument('--save_image', default=False, action="store_true",
                        help='Save YOLO image from the imageData Labelme attribute')
    parser.add_argument('--image_width', help='Set image width if not image saved from imageData',
                        required=False, default=1920)
    parser.add_argument('--image_height', help='Set image height if not image saved from imageData',
                        required=False, default=1080)
    parser.add_argument('--shift_class_id', type=int,
                        help='Shifts the class ID. Useful to change to/from zero based index',
                        required=False, default=0)
    args = parser.parse_args(sys.argv[1:])

    labels_dir = args.labels_dir

    if args.multi_video:
        json_dirs = [os.path.join(labels_dir, dir) for dir in os.listdir(labels_dir)\
                     if os.path.isdir(os.path.join(labels_dir, dir))]
    else:
        json_dirs = [labels_dir]

    for json_dir in json_dirs:
        converter = Labelme2YOLO(json_dir, args=args)
        if args.json_name is None:
            converter.convert(val_size=args.val_size)
        else:
            converter.convert_one(args.json_name)
    
