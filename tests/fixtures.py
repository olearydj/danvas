import json
from pathlib import Path


def write_assignment_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "name": "HW1",
                    "assignment_group_name": "Homework",
                    "published": True,
                    "due_at": "2026-01-10T23:59:00Z",
                    "assignment_group": {"name": "Homework", "group_weight": 40},
                },
                {
                    "name": "Test 1",
                    "assignment_group_name": "Tests",
                    "published": False,
                    "due_at": "",
                    "assignment_group": {"name": "Tests", "group_weight": 60},
                },
            ]
        ),
        encoding="utf-8",
    )


def write_gradebook_fixture(path: Path) -> None:
    path.write_text(
        "Student,ID,Homework (1),Homework Unposted Final Score,Tests Unposted Final Score,Unposted Final Score\n"
        "Points Possible,,10,,,\n"
        '"Doe, Jane",1,90,90,80,85\n'
        '"Smith, Pat",2,N/A,100,90,95\n'
        '"Student, Test",10,0,0,0,0\n',
        encoding="utf-8",
    )


def write_quiz_fixture(path: Path) -> None:
    path.write_text(
        "name,id,sis_id,section,section_id,section_sis_id,submitted,123: Which version of COMP?,0,124: Knowledge,2,n correct,n incorrect,score\n"
        "Doe Jane,10,,,1,,2026-01-01,Python,0,A,2,1,0,2\n"
        "Smith Pat,11,,,1,,2026-01-01,Other,0,B,1,0,1,1\n",
        encoding="utf-8",
    )
