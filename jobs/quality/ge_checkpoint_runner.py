"""
Great Expectations Formal Checkpoint Runner

Provides:
- Formal checkpoint execution with JSON data docs
- MongoDB result storage
- Comprehensive validation reports
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
import pandas as pd
import json
import os

# Import from our GE-style validation module
from great_expectations import (
    NewsDataExpectations,
    ValidationResult,
    ExpectationResult,
    DataQualityCheckpoint
)


class DataDocsGenerator:
    """Generate JSON data documentation from validation results"""
    
    def __init__(self, output_dir: str = "./data_docs"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate(self, result: ValidationResult) -> str:
        """Generate data docs JSON and return file path"""
        
        # Create comprehensive data doc
        data_doc = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "suite_name": result.suite_name,
                "generator_version": "1.0.0"
            },
            "summary": {
                "success": result.success,
                "run_time": result.run_time,
                "statistics": result.statistics
            },
            "expectations": [],
            "failed_expectations": []
        }
        
        for exp_result in result.results:
            exp_doc = {
                "expectation_type": exp_result.expectation_type,
                "success": exp_result.success,
                "column": exp_result.column,
                "details": exp_result.details,
                "timestamp": exp_result.timestamp
            }
            data_doc["expectations"].append(exp_doc)
            
            if not exp_result.success:
                data_doc["failed_expectations"].append(exp_doc)
        
        # Write to file
        filename = f"data_docs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data_doc, f, indent=2, default=str)
        
        print(f"📄 Data docs generated: {filepath}")
        return filepath


class MongoDBResultStore:
    """Store validation results in MongoDB"""
    
    def __init__(self, uri: str = "mongodb://mongodb:27017", 
                 database: str = "news_rt"):
        self.client = MongoClient(uri)
        self.db = self.client[database]
        self.collection = self.db["data_quality_results"]
    
    def store(self, result: ValidationResult, data_docs_path: str = None) -> str:
        """Store validation result and return document ID"""
        
        doc = {
            "suite_name": result.suite_name,
            "run_time": datetime.now(),
            "success": result.success,
            "statistics": result.statistics,
            "expectations": [r.to_dict() for r in result.results],
            "data_docs_path": data_docs_path
        }
        
        insert_result = self.collection.insert_one(doc)
        print(f"📊 Results stored in MongoDB: {insert_result.inserted_id}")
        return str(insert_result.inserted_id)
    
    def get_latest(self) -> Optional[Dict]:
        """Get the latest validation result"""
        return self.collection.find_one(
            sort=[("run_time", -1)]
        )
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get validation history"""
        return list(self.collection.find(
            sort=[("run_time", -1)],
            limit=limit
        ))


class FormalCheckpoint:
    """
    Formal Great Expectations-style Checkpoint
    
    Orchestrates:
    1. Data validation
    2. Data docs generation
    3. MongoDB result storage
    4. Console reporting
    """
    
    def __init__(self, 
                 name: str,
                 mongodb_uri: str = "mongodb://mongodb:27017",
                 data_docs_dir: str = "/tmp/data_docs"):
        self.name = name
        self.expectations = NewsDataExpectations(name)
        self.docs_generator = DataDocsGenerator(data_docs_dir)
        self.result_store = MongoDBResultStore(mongodb_uri)
    
    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Run the full checkpoint pipeline
        
        Returns:
            Dict with validation result, data docs path, and MongoDB ID
        """
        print(f"\n{'='*60}")
        print(f"🔍 GREAT EXPECTATIONS CHECKPOINT: {self.name}")
        print(f"{'='*60}")
        print(f"📅 Run Time: {datetime.now().isoformat()}")
        print(f"📊 Data Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        print(f"{'='*60}\n")
        
        # Step 1: Validate data
        print("Step 1: Running expectations...")
        result = self.expectations.validate(df)
        
        # Step 2: Generate data docs
        print("\nStep 2: Generating data docs...")
        docs_path = self.docs_generator.generate(result)
        
        # Step 3: Store in MongoDB
        print("\nStep 3: Storing results in MongoDB...")
        doc_id = self.result_store.store(result, docs_path)
        
        # Step 4: Print summary
        self._print_summary(result)
        
        return {
            "success": result.success,
            "statistics": result.statistics,
            "data_docs_path": docs_path,
            "mongodb_id": doc_id,
            "result": result
        }
    
    def _print_summary(self, result: ValidationResult):
        """Print formatted validation summary"""
        stats = result.statistics
        
        print(f"\n{'='*60}")
        print("📋 VALIDATION SUMMARY")
        print(f"{'='*60}")
        
        # Overall status
        if result.success:
            print("✅ OVERALL: PASSED")
        else:
            print("❌ OVERALL: FAILED")
        
        print(f"\n📊 Statistics:")
        print(f"   Total Expectations: {stats['total_expectations']}")
        print(f"   Passed: {stats['passed']}")
        print(f"   Failed: {stats['failed']}")
        print(f"   Success Rate: {stats['success_rate']:.1%}")
        
        # Individual results
        print(f"\n📝 Expectation Results:")
        for exp in result.results:
            icon = "✅" if exp.success else "❌"
            col_info = f"[{exp.column}]" if exp.column else "[table]"
            print(f"   {icon} {exp.expectation_type} {col_info}")
            
            if not exp.success and exp.details:
                for key, value in exp.details.items():
                    if key != "error":
                        print(f"      └─ {key}: {value}")
        
        print(f"{'='*60}\n")


def run_formal_checkpoint(mongodb_uri: str = "mongodb://mongodb:27017"):
    """
    Main entry point for running the formal checkpoint
    Connects to MongoDB and validates news data
    """
    print("🚀 Starting Formal Great Expectations Checkpoint...")
    
    # Connect to MongoDB and load data
    client = MongoClient(mongodb_uri)
    db = client["news_analytics"]
    
    # Load articles
    articles = list(db.historical_articles.find({}, limit=5000))
    
    if not articles:
        print("❌ No articles found in database!")
        return None
    
    df = pd.DataFrame(articles)
    print(f"📥 Loaded {len(df)} articles from MongoDB")
    
    # Run checkpoint
    checkpoint = FormalCheckpoint(
        name="news_data_validation",
        mongodb_uri=mongodb_uri,
        data_docs_dir="/tmp/data_docs"
    )
    
    result = checkpoint.run(df)
    
    # Close connection
    client.close()
    
    return result


if __name__ == "__main__":
    # Run the checkpoint
    result = run_formal_checkpoint()
    
    if result:
        print(f"\n🎉 Checkpoint completed!")
        print(f"   Success: {result['success']}")
        print(f"   Data Docs: {result['data_docs_path']}")
        print(f"   MongoDB ID: {result['mongodb_id']}")
