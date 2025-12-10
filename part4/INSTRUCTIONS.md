# Part 4: NBA Embedding Fine-Tuning - Step-by-Step Guide

## Overview

This guide walks you through fine-tuning `intfloat/e5-base-v2` on NBA-specific data to improve retrieval accuracy for my RAG pipeline.

**Time Required:** ~10 minutes  
**Platform:** Google Colab (T4 GPU)  
**Paper Reference:** Wang et al. (2022) "Text Embeddings by Weakly-Supervised Contrastive Pre-training" [arXiv:2212.03533](https://arxiv.org/abs/2212.03533)

---

## Files in `part4/` Folder

| File | Purpose |
|------|---------|
| `training_pairs.json` | 50 NBA query-context pairs (35 train, 5 val, 10 test) |
| `fine_tune_nba.ipynb` | Google Colab notebook |
| `evaluation_results.json` | Experiment results |
| `responses.txt` | Writeup with methodology and results |
| `INSTRUCTIONS.md` | This file |

---

## Step 1: Open Google Colab

1. Go to [colab.research.google.com](https://colab.research.google.com)
2. Click **File → Upload notebook**
3. Upload `fine_tune_nba.ipynb` from my `part4/` folder

---

## Step 2: Enable GPU Runtime

1. Click **Runtime → Change runtime type**
2. Select **T4 GPU** from the Hardware accelerator dropdown
3. Click **Save**

---

## Step 3: Run Cell 1 - Install Dependencies

```python
!pip install -q sentence-transformers
```

Wait ~30 seconds for installation.

---

## Step 4: Run Cell 2 - Upload Training Data

```python
from google.colab import files
uploaded = files.upload()
```

When the file picker appears:
1. Click **Choose Files**
2. Select `training_pairs.json` from my `part4/` folder
3. Wait for upload to complete

---

## Step 5: Run Cell 3 - Verify Data

```python
import json

with open('training_pairs.json', 'r') as f:
    data = json.load(f)

train_pairs = [p for p in data['training_pairs'] if p['split'] == 'train']
val_pairs = [p for p in data['training_pairs'] if p['split'] == 'validation']
test_pairs = [p for p in data['training_pairs'] if p['split'] == 'test']

print(f"✅ Training pairs: {len(train_pairs)}")
print(f"✅ Validation pairs: {len(val_pairs)}")
print(f"✅ Test pairs: {len(test_pairs)}")
```

**Expected Output:**
```
✅ Training pairs: 35
✅ Validation pairs: 5
✅ Test pairs: 10
```

---

## Step 6: Run Cell 4 - Fine-Tune Model

This is the main training cell. When prompted by wandb, enter **3** to skip logging.

**Expected Output:**
```
Loading intfloat/e5-base-v2...
🚀 Fine-tuning on 35 NBA examples...
Epoch 1: 100%|██████████| 5/5 [00:15<00:00]
Epoch 2: 100%|██████████| 5/5 [00:14<00:00]
Epoch 3: 100%|██████████| 5/5 [00:14<00:00]
✅ Training complete in ~109 seconds
```

---

## Step 7: Run Cell 5 - Evaluate Models

This compares baseline E5 vs. my fine-tuned model on the 10 held-out test queries.

**Expected Output:**
```
Loading baseline model...
Loading fine-tuned model...
📊 Evaluating baseline (pre-trained E5)...
📊 Evaluating fine-tuned (E5-NBA)...
```

---

## Step 8: Run Cell 6 - View Results

```
======================================================================
🏀 NBA RAG FINE-TUNING RESULTS
======================================================================
Metric       E5-base-v2         E5-NBA (tuned)     Improvement 
----------------------------------------------------------------------
Recall@1     0.0%               10.0%                   +10 pp
Recall@5     90.0%              100.0%                  +11.1%
MRR          0.281              0.293                   +4.5%
======================================================================
```

---

## Step 9: Run Cell 7 - Download Results

This saves `evaluation_results.json` containing my metrics.

Click the download link that appears to save the file to your computer.
