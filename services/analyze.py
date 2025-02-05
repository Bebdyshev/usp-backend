import pandas as pd
from io import StringIO

def analyze_excel(csv_text):

    df = pd.read_csv(StringIO(csv_text))

    result = []

    for index, row in df.iterrows():

        if row.isna().all():
            continue
        student_name = str(row[0]).split(',')[0].strip()  
        
        try:
            actual_scores = [None if pd.isna(score) else float(score) for score in row[1:5].tolist()]
        except ValueError:
            continue  

        try:
            predicted_scores = [None if pd.isna(score) else float(score) for score in row[5:9].tolist()]
        except ValueError:
            continue  
        actual_scores.append(0.0)
    
        predicted_scores.append(0.0)
        
        student_data = {
            "student_name": student_name,
            "actual_score": actual_scores,
            "predicted_score": predicted_scores
        }

        result.append(student_data)

    print(result)

    try:
        return result
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error decoding GPT response.")

def replace_nan_with_zero(scores):
    return [score if score is not None else 0.0 for score in scores]