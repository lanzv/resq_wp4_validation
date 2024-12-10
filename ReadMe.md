# RES-Q Dataset Evaluation Script

The evaluation script validates the correctness and consistency of the WP4 RES-Q dataset.


## Usage

```python
from form_definition import FormDefinition

form_definition = FormDefinition(schema_path="./schema.json")

data = {
    "data": [
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        ...
    ]
}

form_definition.validate_dataset(dataset=data, required_fields_validation=True)
```

Eventually, only single report could be validated as well
```python
from form_definition import FormDefinition

form_definition = FormDefinition(schema_path="./schema.json")

data = {
    "data": [
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        {"report_id": .., "paragraphs": .., ...}, 
        ...
    ]
}

form_definition.validate_report(dataset=data["data"][4], required_fields_validation=True)
```

In case you want to ignore the required fields validation (the validation against the schema itself with its dynamic structure), set the parameter ```required_fields_validation = False```

To see the list of strigified possible options (with its ranges in case of integers and numbers) for all questions, use the ```possible_options``` property:
```python
form_definition = FormDefinition(schema_path="./schema.json")
# list all strigified possible options for all questions
for qa_id in form_definition.possible_options:
    print("{}: {}".format(qa_id, [str(op) for op in form_definition.possible_options[qa_id]]))
```

To see the list of the exact correct types of possible options (None != 'None', True != 'True') ..
```python
form_definition = FormDefinition(schema_path="./schema.json")
# list all possible otpions in the correct forms for all questions
for qa_id in form_definition.possible_options:
    print("{}: {}".format(qa_id, [op for op in form_definition.possible_options[qa_id]]))
```
