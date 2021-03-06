#!/usr/bin/env python

import numpy as np
import pandas as pd
import click as ck
from sklearn.metrics import classification_report
from sklearn.metrics.pairwise import cosine_similarity
import sys
from collections import deque
import time
import logging
from sklearn.metrics import roc_curve, auc, matthews_corrcoef
from scipy.spatial import distance
from scipy import sparse
import math
from utils import FUNC_DICT, Ontology, NAMESPACES
from matplotlib import pyplot as plt

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)


@ck.command()
@ck.option(
    '--train-data-file', '-trdf', default='data/human.pkl',
    help='Data file with training features')
@ck.option(
    '--test-data-file', '-tsdf', default='data/predictions.pkl',
    help='Test data file')
@ck.option(
    '--terms-file', '-tf', default='data/terms.pkl',
    help='Data file with sequences and complete set of annotations')
@ck.option(
    '--rules-file', '-rf', default='data/rules_hp.txt',
    help='Data file with sequences and complete set of annotations')
def main(train_data_file, test_data_file, terms_file, rules_file):

    hp = Ontology('data/hp.obo', with_rels=True)
    terms_df = pd.read_pickle(terms_file)
    terms = terms_df['terms'].values.flatten()
    terms_dict = {v: i for i, v in enumerate(terms)}

    train_df = pd.read_pickle(train_data_file)

    rule_annots = {}
    with open(rules_file) as f:
        for line in f:
            it = line.strip().split()
            go_id = it[0].replace('_', ':')
            hp_id = it[1].replace('_', ':')
            if go_id not in rule_annots:
                rule_annots[go_id] = set()
            rule_annots[go_id].add(hp_id)
        
    test_df = pd.read_pickle(test_data_file)
    annotations = train_df['hp_annotations'].values
    annotations = list(map(lambda x: set(x), annotations))
    test_annotations = test_df['hp_annotations'].values
    test_annotations = list(map(lambda x: set(x), test_annotations))
    hp.calculate_ic(annotations)

    hp_set = set(terms)
    
    hp_set_anch = set()
    for hp_id in hp_set:
        hp_set_anch |= hp.get_anchestors(hp_id)
    
    labels = test_annotations
    # labels = list(map(lambda x: set(filter(lambda y: y in hp_set_anch, x)), labels))
    
    fmax = 0.0
    tmax = 0.0
    precisions = []
    recalls = []
    smin = 1000000.0
    max_preds = None
    for t in range(0, 101):
        threshold = t / 100.0
        preds = []
        for i, row in enumerate(test_df.itertuples()):
            gene_id = row.genes
            annots = set()
            for item in row.deepgo_annotations:
                go_id, score = item.split('|')
                score = float(score)
                if score >= threshold and go_id in rule_annots:
                    annots |= rule_annots[go_id]
            new_annots = set()
            for hp_id in annots:
                new_annots |= hp.get_anchestors(hp_id)

            preds.append(new_annots)
        
    
        # Filter classes
        
        fscore, prec, rec, s = evaluate_annotations(hp, labels, preds)
        precisions.append(prec)
        recalls.append(rec)
        print(f'Fscore: {fscore}, S: {s}, threshold: {threshold}')
        if fmax < fscore:
            fmax = fscore
            tmax = threshold
            max_preds = preds
        if smin > s:
            smin = s
    print(f'Fmax: {fmax:0.3f}, Smin: {smin:0.3f}, threshold: {tmax}')
    test_df['hp_preds'] = max_preds
    test_df.to_pickle('data/predictions_max.pkl')
    precisions = np.array(precisions)
    recalls = np.array(recalls)
    sorted_index = np.argsort(recalls)
    recalls = recalls[sorted_index]
    precisions = precisions[sorted_index]
    aupr = np.trapz(precisions, recalls)
    print(f'AUPR: {aupr:0.3f}')
    # plt.figure()
    # lw = 2
    # plt.plot(recalls, precisions, color='darkorange',
    #          lw=lw, label=f'AUPR curve (area = {aupr:0.2f})')
    # plt.xlim([0.0, 1.0])
    # plt.ylim([0.0, 1.05])
    # plt.xlabel('Recall')
    # plt.ylabel('Precision')
    # plt.title('Area Under the Precision-Recall curve')
    # plt.legend(loc="lower right")
    # df = pd.DataFrame({'precisions': precisions, 'recalls': recalls})
    # df.to_pickle(f'PR.pkl')

def compute_roc(labels, preds):
    # Compute ROC curve and ROC area for each class
    fpr, tpr, _ = roc_curve(labels.flatten(), preds.flatten())
    roc_auc = auc(fpr, tpr)
    return roc_auc

def compute_mcc(labels, preds):
    # Compute ROC curve and ROC area for each class
    mcc = matthews_corrcoef(labels.flatten(), preds.flatten())
    return mcc

def evaluate_annotations(go, real_annots, pred_annots):
    total = 0
    p = 0.0
    r = 0.0
    p_total= 0
    ru = 0.0
    mi = 0.0
    for i in range(len(real_annots)):
        if len(real_annots[i]) == 0:
            continue
        tp = set(real_annots[i]).intersection(set(pred_annots[i]))
        fp = pred_annots[i] - tp
        fn = real_annots[i] - tp
        for go_id in fp:
            mi += go.get_ic(go_id)
        for go_id in fn:
            ru += go.get_ic(go_id)
        tpn = len(tp)
        fpn = len(fp)
        fnn = len(fn)
        total += 1
        recall = tpn / (1.0 * (tpn + fnn))
        r += recall
        if len(pred_annots[i]) > 0:
            p_total += 1
            precision = tpn / (1.0 * (tpn + fpn))
            p += precision
    ru /= total
    mi /= total
    r /= total
    if p_total > 0:
        p /= p_total
    f = 0.0
    if p + r > 0:
        f = 2 * p * r / (p + r)
    s = math.sqrt(ru * ru + mi * mi)
    return f, p, r, s


if __name__ == '__main__':
    main()
