import sys
sys.path.insert(0, "/app")
from config import SessionLocal
from schemas.models import *
db = SessionLocal()
db.query(StudentInDB).delete()
db.query(GradeInDB).delete()
db.commit()
db.close()
print("Done")
