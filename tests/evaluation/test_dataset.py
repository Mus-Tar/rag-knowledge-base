import json
from pathlib import Path


def test_fixed_evaluation_dataset_has_valid_references() -> None:
    dataset_path = Path(__file__).parents[2] / "evaluation" / "qa_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    filenames = {document["filename"] for document in dataset["documents"]}
    question_ids = [question["id"] for question in dataset["questions"]]

    assert dataset["schema_version"] == 1
    assert len(dataset["documents"]) == 10
    assert len(dataset["questions"]) == 20
    assert len(question_ids) == len(set(question_ids))
    assert all(question["relevant_filename"] in filenames for question in dataset["questions"])
    assert all(question["expected_answer_terms"] for question in dataset["questions"])
