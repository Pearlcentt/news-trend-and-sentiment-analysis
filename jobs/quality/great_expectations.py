"""
Great Expectations Data Quality Validation
Based on IT4931 Great_Expectations_lab

Provides automated data quality checks for the news pipeline:
- Schema validation
- Null checking
- Value range validation
- Freshness checks
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os


class ExpectationResult:
    """Result of a single expectation check"""
    def __init__(self, success: bool, expectation_type: str, 
                 column: Optional[str] = None, details: Optional[Dict] = None):
        self.success = success
        self.expectation_type = expectation_type
        self.column = column
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'expectation_type': self.expectation_type,
            'column': self.column,
            'details': self.details,
            'timestamp': self.timestamp
        }


class ValidationResult:
    """Aggregated validation results"""
    def __init__(self, suite_name: str):
        self.suite_name = suite_name
        self.results: List[ExpectationResult] = []
        self.run_time = datetime.now().isoformat()
        self.success = True
    
    def add_result(self, result: ExpectationResult):
        self.results.append(result)
        if not result.success:
            self.success = False
    
    @property
    def statistics(self) -> Dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        return {
            'total_expectations': total,
            'passed': passed,
            'failed': total - passed,
            'success_rate': passed / total if total > 0 else 0.0
        }
    
    def to_dict(self) -> Dict:
        return {
            'suite_name': self.suite_name,
            'run_time': self.run_time,
            'success': self.success,
            'statistics': self.statistics,
            'results': [r.to_dict() for r in self.results]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class NewsDataExpectations:
    """
    Great Expectations-style validation for news data
    Implements common expectations for data quality
    """
    
    def __init__(self, suite_name: str = "news_data_suite"):
        self.suite_name = suite_name
    
    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """Run all expectations against the dataframe"""
        result = ValidationResult(self.suite_name)
        
        # Schema expectations - using actual news schema column names
        result.add_result(self.expect_columns_to_exist(
            df, ['article_id', 'title', 'source_domain', 'event_time']
        ))
        
        # Null expectations
        result.add_result(self.expect_column_values_to_not_be_null(df, 'article_id'))
        result.add_result(self.expect_column_values_to_not_be_null(df, 'title'))
        result.add_result(self.expect_column_values_to_not_be_null(df, 'source_domain'))
        
        # Uniqueness expectations
        result.add_result(self.expect_column_values_to_be_unique(df, 'article_id'))
        
        # String length expectations
        result.add_result(self.expect_column_value_lengths_to_be_between(
            df, 'title', min_length=10, max_length=500
        ))
        
        # Value set expectations
        if 'sentiment' in df.columns:
            result.add_result(self.expect_column_values_to_be_in_set(
                df, 'sentiment', ['positive', 'negative', 'neutral']
            ))
        
        # Freshness expectations
        if 'event_time' in df.columns:
            result.add_result(self.expect_column_values_to_be_recent(
                df, 'event_time', max_age_hours=72
            ))
        
        # Row count expectations
        result.add_result(self.expect_table_row_count_to_be_between(
            df, min_count=1, max_count=1000000
        ))
        
        return result
    
    def expect_columns_to_exist(self, df: pd.DataFrame, 
                                 columns: List[str]) -> ExpectationResult:
        """Expect specified columns to exist in the dataframe"""
        missing = [c for c in columns if c not in df.columns]
        success = len(missing) == 0
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_columns_to_exist',
            details={
                'expected_columns': columns,
                'missing_columns': missing,
                'actual_columns': list(df.columns)
            }
        )
    
    def expect_column_values_to_not_be_null(self, df: pd.DataFrame, 
                                            column: str) -> ExpectationResult:
        """Expect column to have no null values"""
        if column not in df.columns:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_values_to_not_be_null',
                column=column,
                details={'error': f'Column {column} not found'}
            )
        
        null_count = df[column].isnull().sum()
        total_count = len(df)
        success = null_count == 0
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_column_values_to_not_be_null',
            column=column,
            details={
                'null_count': int(null_count),
                'total_count': total_count,
                'null_percentage': null_count / total_count if total_count > 0 else 0
            }
        )
    
    def expect_column_values_to_be_unique(self, df: pd.DataFrame, 
                                          column: str) -> ExpectationResult:
        """Expect column values to be unique"""
        if column not in df.columns:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_values_to_be_unique',
                column=column,
                details={'error': f'Column {column} not found'}
            )
        
        total_count = len(df)
        unique_count = df[column].nunique()
        duplicate_count = total_count - unique_count
        success = duplicate_count == 0
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_column_values_to_be_unique',
            column=column,
            details={
                'unique_count': unique_count,
                'duplicate_count': duplicate_count,
                'total_count': total_count
            }
        )
    
    def expect_column_value_lengths_to_be_between(self, df: pd.DataFrame, 
                                                   column: str,
                                                   min_length: int = 0,
                                                   max_length: int = 1000) -> ExpectationResult:
        """Expect string column values to have lengths within range"""
        if column not in df.columns:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_value_lengths_to_be_between',
                column=column,
                details={'error': f'Column {column} not found'}
            )
        
        lengths = df[column].astype(str).str.len()
        violations = ((lengths < min_length) | (lengths > max_length)).sum()
        success = violations == 0
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_column_value_lengths_to_be_between',
            column=column,
            details={
                'min_length': min_length,
                'max_length': max_length,
                'actual_min': int(lengths.min()),
                'actual_max': int(lengths.max()),
                'violations': int(violations)
            }
        )
    
    def expect_column_values_to_be_in_set(self, df: pd.DataFrame, 
                                          column: str,
                                          value_set: List[Any]) -> ExpectationResult:
        """Expect column values to be within a specified set"""
        if column not in df.columns:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_values_to_be_in_set',
                column=column,
                details={'error': f'Column {column} not found'}
            )
        
        invalid_values = df[~df[column].isin(value_set)][column].unique().tolist()
        success = len(invalid_values) == 0
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_column_values_to_be_in_set',
            column=column,
            details={
                'expected_set': value_set,
                'invalid_values': invalid_values[:10]  # Limit to first 10
            }
        )
    
    def expect_column_values_to_be_recent(self, df: pd.DataFrame, 
                                          column: str,
                                          max_age_hours: int = 24) -> ExpectationResult:
        """Expect datetime column values to be within max_age_hours"""
        if column not in df.columns:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_values_to_be_recent',
                column=column,
                details={'error': f'Column {column} not found'}
            )
        
        try:
            timestamps = pd.to_datetime(df[column])
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            old_count = (timestamps < cutoff).sum()
            success = old_count == 0
            
            return ExpectationResult(
                success=success,
                expectation_type='expect_column_values_to_be_recent',
                column=column,
                details={
                    'max_age_hours': max_age_hours,
                    'old_records_count': int(old_count),
                    'oldest_timestamp': str(timestamps.min()),
                    'newest_timestamp': str(timestamps.max())
                }
            )
        except Exception as e:
            return ExpectationResult(
                success=False,
                expectation_type='expect_column_values_to_be_recent',
                column=column,
                details={'error': str(e)}
            )
    
    def expect_table_row_count_to_be_between(self, df: pd.DataFrame,
                                              min_count: int = 0,
                                              max_count: int = 1000000) -> ExpectationResult:
        """Expect table to have row count within range"""
        row_count = len(df)
        success = min_count <= row_count <= max_count
        
        return ExpectationResult(
            success=success,
            expectation_type='expect_table_row_count_to_be_between',
            details={
                'min_count': min_count,
                'max_count': max_count,
                'actual_count': row_count
            }
        )


class DataQualityCheckpoint:
    """
    Checkpoint runner for data quality validation
    Similar to Great Expectations Checkpoint
    """
    
    def __init__(self, name: str, expectations: NewsDataExpectations,
                 result_dir: str = "./data_quality_results"):
        self.name = name
        self.expectations = expectations
        self.result_dir = result_dir
        os.makedirs(result_dir, exist_ok=True)
    
    def run(self, df: pd.DataFrame, save_result: bool = True) -> ValidationResult:
        """Run checkpoint and optionally save results"""
        result = self.expectations.validate(df)
        
        if save_result:
            result_file = os.path.join(
                self.result_dir,
                f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(result_file, 'w') as f:
                f.write(result.to_json())
            print(f"Data quality results saved to: {result_file}")
        
        # Print summary
        stats = result.statistics
        print(f"\n{'='*50}")
        print(f"Data Quality Checkpoint: {self.name}")
        print(f"{'='*50}")
        print(f"Overall Success: {'✅ PASSED' if result.success else '❌ FAILED'}")
        print(f"Total Expectations: {stats['total_expectations']}")
        print(f"Passed: {stats['passed']}")
        print(f"Failed: {stats['failed']}")
        print(f"Success Rate: {stats['success_rate']:.1%}")
        print(f"{'='*50}\n")
        
        return result


# Convenience functions
def validate_news_dataframe(df: pd.DataFrame, 
                           suite_name: str = "news_validation") -> ValidationResult:
    """Quick validation of a news dataframe"""
    expectations = NewsDataExpectations(suite_name)
    return expectations.validate(df)


def run_checkpoint(df: pd.DataFrame, 
                  checkpoint_name: str = "news_checkpoint") -> ValidationResult:
    """Run a full checkpoint with result saving"""
    expectations = NewsDataExpectations()
    checkpoint = DataQualityCheckpoint(checkpoint_name, expectations)
    return checkpoint.run(df)


if __name__ == "__main__":
    # Demo usage
    import random
    
    # Create sample data
    sample_data = pd.DataFrame({
        'id': [f'news_{i}' for i in range(100)],
        'title': [f'Sample News Article {i} About Technology' for i in range(100)],
        'source': random.choices(['Guardian', 'Reuters', 'BBC', 'CNN'], k=100),
        'published_at': [datetime.now() - timedelta(hours=random.randint(0, 48)) 
                        for _ in range(100)],
        'sentiment': random.choices(['positive', 'negative', 'neutral'], k=100),
        'category': random.choices(['Tech', 'Sports', 'Politics'], k=100)
    })
    
    # Run validation
    result = run_checkpoint(sample_data, "demo_checkpoint")
    
    # Print detailed results
    for r in result.results:
        status = "✅" if r.success else "❌"
        print(f"{status} {r.expectation_type}: {r.column or 'table'}")
