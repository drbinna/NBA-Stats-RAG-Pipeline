#!/usr/bin/env python3
"""
Test script for fine_tune_nba.ipynb
Tests data loading and validation without requiring GPU or full training
"""

import json
import os
import sys

def test_data_loading():
    """Test Step 3: Load and Verify Data"""
    print("=" * 70)
    print("Testing Step 3: Load and Verify Data")
    print("=" * 70)
    
    training_pairs_path = os.path.join(os.path.dirname(__file__), 'training_pairs.json')
    
    if not os.path.exists(training_pairs_path):
        print(f"❌ ERROR: {training_pairs_path} not found")
        return False
    
    try:
        with open(training_pairs_path, 'r') as f:
            data = json.load(f)
        
        # Split data
        train_pairs = [p for p in data['training_pairs'] if p['split'] == 'train']
        val_pairs = [p for p in data['training_pairs'] if p['split'] == 'validation']
        test_pairs = [p for p in data['training_pairs'] if p['split'] == 'test']
        
        print(f"✅ Training pairs: {len(train_pairs)}")
        print(f"✅ Validation pairs: {len(val_pairs)}")
        print(f"✅ Test pairs: {len(test_pairs)}")
        print(f"\n📊 Total: {len(data['training_pairs'])} pairs")
        
        # Preview examples
        print(f"\n--- Sample Training Pair ---")
        if len(train_pairs) > 0:
            print(f"Query: {train_pairs[0]['query']}")
            print(f"Context: {train_pairs[0]['positive'][:100]}...")
        else:
            print("⚠️ No training pairs available to preview")
            return False
        
        # Validate structure
        required_fields = ['query', 'positive', 'game_id', 'split']
        for pair in train_pairs[:5]:  # Check first 5
            for field in required_fields:
                if field not in pair:
                    print(f"❌ ERROR: Missing required field '{field}' in training pair")
                    return False
        
        print("\n✅ Data loading test passed!")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in training_pairs.json: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_structure():
    """Test that all pairs have required fields"""
    print("\n" + "=" * 70)
    print("Testing Data Structure")
    print("=" * 70)
    
    training_pairs_path = os.path.join(os.path.dirname(__file__), 'training_pairs.json')
    
    try:
        with open(training_pairs_path, 'r') as f:
            data = json.load(f)
        
        all_pairs = data['training_pairs']
        required_fields = ['id', 'query', 'positive', 'source', 'game_id', 'split']
        
        errors = []
        for i, pair in enumerate(all_pairs):
            for field in required_fields:
                if field not in pair:
                    errors.append(f"Pair {i} (id={pair.get('id', 'unknown')}): missing '{field}'")
        
        if errors:
            print("❌ Data structure errors found:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")
            return False
        
        print(f"✅ All {len(all_pairs)} pairs have required fields")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_evaluation_logic():
    """Test evaluation function structure (without running actual model)"""
    print("\n" + "=" * 70)
    print("Testing Evaluation Logic Structure")
    print("=" * 70)
    
    training_pairs_path = os.path.join(os.path.dirname(__file__), 'training_pairs.json')
    
    try:
        with open(training_pairs_path, 'r') as f:
            data = json.load(f)
        
        all_pairs = data['training_pairs']
        test_pairs = [p for p in all_pairs if p['split'] == 'test']
        
        # Build corpus and indices (simulating Step 5)
        corpus = [p['positive'] for p in all_pairs]
        corpus_indices = {p['game_id']: i for i, p in enumerate(all_pairs)}
        
        # Check that all test pairs have game_ids in corpus_indices
        missing_ids = []
        for test_pair in test_pairs:
            game_id = test_pair.get('game_id')
            if game_id not in corpus_indices:
                missing_ids.append(game_id)
        
        if missing_ids:
            print(f"⚠️ WARNING: {len(missing_ids)} test pairs have game_ids not in corpus")
            print(f"  Example missing IDs: {missing_ids[:5]}")
        else:
            print(f"✅ All {len(test_pairs)} test pairs have game_ids in corpus")
        
        print(f"✅ Corpus size: {len(corpus)}")
        print(f"✅ Corpus indices: {len(corpus_indices)} unique game_ids")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n🧪 Testing Fine-Tuning Notebook Components\n")
    
    tests = [
        ("Data Loading", test_data_loading),
        ("Data Structure", test_data_structure),
        ("Evaluation Logic", test_evaluation_logic),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Notebook structure is valid.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
