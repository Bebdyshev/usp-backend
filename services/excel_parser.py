import pandas as pd
from fastapi import HTTPException
from io import BytesIO
import json
import re
from typing import Dict, List, Optional, Tuple, Any
import unicodedata

def normalize_name(name: str) -> str:
    """Normalize student name for consistent storage"""
    if not name or pd.isna(name):
        return ""
    
    # Convert to string and strip whitespace
    name = str(name).strip()
    
    # Unicode normalization
    name = unicodedata.normalize('NFKC', name)
    
    # Remove extra spaces between words
    name = re.sub(r'\s+', ' ', name)
    
    # Remove any trailing commas or periods
    name = name.rstrip('.,')
    
    return name

def validate_percentage(value: Any) -> Optional[float]:
    """Validate and convert percentage value"""
    if pd.isna(value) or value == "" or value is None:
        return None
    
    try:
        # Convert to float
        percent = float(value)
        
        # Validate range (0-100)
        if 0 <= percent <= 100:
            return percent
        else:
            return None
    except (ValueError, TypeError):
        return None

def calculate_predicted_scores_by_quarter(
    previous_class_score: Optional[float],
    current_quarters: List[Optional[float]],
    teacher_percent: Optional[float],
    weights: Dict[str, float] = None
) -> List[float]:
    """
    Calculate predicted scores for each quarter based on available data
    
    Formula for each quarter Qn:
    P(Qn) = (w_prev * prev_class_score) + (w_teacher * teacher_score) + (w_quarters * avg(Q1...Qn-1))
    
    Args:
        previous_class_score: Score from previous class (previous year)
        current_quarters: List of 4 quarter scores (can contain None for future quarters)
        teacher_percent: Teacher's assessment percentage
        weights: Dictionary with weights for 'previous_class', 'teacher', 'quarters'
    
    Returns:
        List of 4 predicted scores, one for each quarter
    """
    if weights is None:
        weights = {
            'previous_class': 0.3,
            'teacher': 0.2,
            'quarters': 0.5
        }
    
    w_prev = weights.get('previous_class', 0.3)
    w_teacher = weights.get('teacher', 0.2)
    w_quarters = weights.get('quarters', 0.5)

    predicted_scores = [0.0] * 4

    # --- P(Q1) ---
    # For Q1, prediction is based on previous class and teacher scores.
    # We need to normalize the weights as there are no previous quarters.
    base_prediction_components = []
    total_base_weight = 0
    
    if previous_class_score is not None:
        base_prediction_components.append(w_prev * previous_class_score)
        total_base_weight += w_prev
        
    if teacher_percent is not None:
        base_prediction_components.append(w_teacher * teacher_percent)
        total_base_weight += w_teacher

    if total_base_weight > 0:
        normalized_prediction = sum(base_prediction_components) / total_base_weight
        predicted_scores[0] = round(normalized_prediction, 1)
    else:
        predicted_scores[0] = 0.0

    # --- P(Q2), P(Q3), P(Q4) ---
    for i in range(1, 4):
        prev_quarters = [q for q in current_quarters[:i] if q is not None and q > 0]
        
        if not prev_quarters:
            # If no previous quarters, prediction is the same as for Q1
            predicted_scores[i] = predicted_scores[0]
            continue
            
        avg_prev_quarters = sum(prev_quarters) / len(prev_quarters)
        
        prediction = (
            (w_prev * previous_class_score if previous_class_score is not None else 0) +
            (w_teacher * teacher_percent if teacher_percent is not None else 0) +
            (w_quarters * avg_prev_quarters)
        )
        predicted_scores[i] = round(prediction, 1)

    return predicted_scores

def parse_excel_grades(
    file_content: bytes,
    expected_columns: Dict[str, List[str]] = None,
    weights: Dict[str, float] = None
) -> Dict[str, Any]:
    """
    Parse Excel file for grade upload
    
    Expected columns (case-insensitive, flexible matching):
    - ФИО / Name / Student Name
    - Процент за 1 предыдущий класс / Previous Class Score / Previous Year %
    - Q1 / Четверть 1 / Quarter 1
    - Q2 / Четверть 2 / Quarter 2  
    - Q3 / Четверть 3 / Quarter 3
    - Q4 / Четверть 4 / Quarter 4
    - Учитель / Teacher / Teacher %
    
    Args:
        file_content: Excel file content as bytes
        expected_columns: Dictionary mapping field names to possible column name aliases
        weights: Dictionary with weights for prediction calculation
    """
    
    if expected_columns is None:
        expected_columns = {
            'name': ['фио', 'имя', 'name', 'student', 'студент', 'ученик'],
            'previous_class': ['процент за 1 предыдущий класс', 'previous class', 'previous year', 'предыдущий класс', 'предыдущий год', 'prev class'],
            'q1': ['q1', 'четверть 1', 'quarter 1', '1 четверть', 'ч1'],
            'q2': ['q2', 'четверть 2', 'quarter 2', '2 четверть', 'ч2'],
            'q3': ['q3', 'четверть 3', 'quarter 3', '3 четверть', 'ч3'],
            'q4': ['q4', 'четверть 4', 'quarter 4', '4 четверть', 'ч4'],
            'teacher': ['учитель', 'teacher', 'преподаватель', 'препод']
        }
    
    if weights is None:
        weights = {
            'previous_class': 0.3,
            'teacher': 0.2,
            'quarters': 0.5
        }
    
    try:
        # Read Excel file
        excel_data = BytesIO(file_content)
        df = pd.read_excel(excel_data, sheet_name=0, header=0)
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Excel file is empty")
        
        # Normalize column names for matching
        df.columns = df.columns.astype(str)
        normalized_columns = {col: col.lower().strip() for col in df.columns}
        
        # Find column mappings
        column_mapping = {}
        
        for field, possible_names in expected_columns.items():
            found = False
            for col_name, normalized in normalized_columns.items():
                if any(possible in normalized for possible in possible_names):
                    column_mapping[field] = col_name
                    found = True
                    break
            
            if not found and field == 'name':
                # Name column is required
                raise HTTPException(
                    status_code=400, 
                    detail=f"Required column not found: {field}. Available columns: {list(df.columns)}"
                )
        
        # Parse student data
        students_data = []
        warnings = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if row.isna().all():
                    continue
                
                # Get student name (required)
                student_name = normalize_name(row.get(column_mapping.get('name', '')))
                if not student_name:
                    warnings.append(f"Row {index + 2}: Missing student name, skipped")
                    continue
                
                # Parse percentages
                previous_class_score = validate_percentage(row.get(column_mapping.get('previous_class')))
                teacher_percent = validate_percentage(row.get(column_mapping.get('teacher')))
                
                # Parse quarterly grades
                quarters = []
                for quarter in ['q1', 'q2', 'q3', 'q4']:
                    col = column_mapping.get(quarter)
                    if col:
                        quarter_value = validate_percentage(row.get(col))
                        quarters.append(quarter_value)
                    else:
                        quarters.append(None)
                
                # Calculate predicted scores for each quarter
                predicted_scores = calculate_predicted_scores_by_quarter(
                    previous_class_score, quarters, teacher_percent, weights
                )
                
                # Prepare actual scores (replace None with 0.0 for calculations)
                actual_scores = [q if q is not None else 0.0 for q in quarters]
                
                student_data = {
                    "student_name": student_name,
                    "previous_class_score": previous_class_score,
                    "current_quarters": quarters,
                    "teacher_percent": teacher_percent,
                    "actual_scores": actual_scores,
                    "predicted_scores": predicted_scores
                }
                
                students_data.append(student_data)
                
            except Exception as e:
                errors.append(f"Row {index + 2}: Error processing data - {str(e)}")
                continue
        
        if not students_data:
            raise HTTPException(
                status_code=400, 
                detail="No valid student data found in Excel file"
            )
        
        response = {
            "students": students_data,
            "total_rows": len(df),
            "processed_rows": len(students_data),
            "warnings": warnings,
            "errors": errors,
            "column_mapping": column_mapping
        }
        
        return response
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Excel file is empty or corrupted")
    except pd.errors.ParserError as e:
        raise HTTPException(status_code=400, detail=f"Error parsing Excel file: {str(e)}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Unexpected error processing Excel file: {str(e)}")

def generate_excel_template() -> bytes:
    """Generate Excel template with proper column headers"""
    
    template_data = {
        'ФИО': ['Иванов Иван Иванович', 'Петров Петр Петрович', 'Сидорова Анна Владимировна'],
        'Процент за 1 предыдущий класс, %': [85.5, 92.0, 78.3],
        'Q1, %': [88, 90, 82],
        'Q2, %': [85, 94, 79],
        'Q3, %': [None, 89, 85],  # Example of missing quarter
        'Q4, %': [None, None, None],  # Future quarters
        'Учитель, %': [87, 91, 80]
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Grades', index=False)
        
        # Format the worksheet
        worksheet = writer.sheets['Grades']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output.getvalue()



