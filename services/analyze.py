import pandas as pd
from fastapi import HTTPException
from io import StringIO
import json

def analyze_excel(csv_text):
    try:
        df = pd.read_csv(StringIO(csv_text), header=None, dtype=str)  # Читаем CSV как строки для избежания ошибок

        # Поиск строки, содержащей "Предмет"
        subject_row = df[df[0].astype(str).str.contains("Предмет", na=False, case=False, regex=False)]

        if not subject_row.empty:
            subject = subject_row.iloc[0, 1] if pd.notna(subject_row.iloc[0, 1]) else "Неизвестный предмет"
        else:
            subject = "Неизвестный предмет"

        result = []

        for index, row in df.iloc[2:].iterrows():  # Пропускаем заголовки
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

        response = {
            "subject": subject,  
            "students": result
        }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

def replace_nan_with_zero(scores):
    return [score if score is not None else 0.0 for score in scores]
