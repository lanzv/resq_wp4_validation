import json
import logging
from jsonschema import validate, ValidationError
from datetime import datetime

class FormDefinition:
    """Class to define and validate forms based on a given JSON schema."""

    def __init__(self, schema_path="./resources/schema_3_1_7.json"):
        """
        Initializes the FormDefinition with a JSON schema.

        Args:
            schema_path (str): The path to the JSON schema file. Defaults to "./resources/schema_3_1_7.json".
        """
        with open(schema_path, 'r') as file:
            self.schema = json.load(file)

        # Set to store all question IDs and their possible options
        self.question_ids = set()
        self.possible_options = {}
        self._extract_question_ids(self.schema, '')

    def _extract_question_ids(self, data, base_id):
        """
        Recursively loads question IDs and their possible options from the schema data.

        Args:
            data (dict or list): The schema data to parse.
            base_id (str): The base ID used for constructing question IDs.
        """        
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "properties":
                    for prop_id in value:
                        self._extract_question_ids(value[prop_id], f"{base_id}.{prop_id}" if base_id else prop_id)
                else:
                    self._extract_question_ids(value, base_id)

                if "type" in data and data['type'] != 'object':
                    data_types = data["type"] if isinstance(data["type"], list) else [data["type"]]
                    for dtype in data_types:
                        self._add_options(base_id, FormDefinition._get_data_options(dtype, data))
                    self.question_ids.add(base_id)
                elif "enum" in data:
                    self._add_options(base_id, FormDefinition._get_data_options("string", data))
                    self.question_ids.add(base_id)

        elif isinstance(data, list):
            for item in data:
                self._extract_question_ids(item, base_id)

    def _add_options(self, question_id, options):
        """Adds new options for a given question ID."""
        if question_id not in self.possible_options:
            self.possible_options[question_id] = set()

        for new_option in options:
            existing_option = next((opt for opt in self.possible_options[question_id]
                                    if isinstance(opt, type(new_option)) and not isinstance(opt, str)), None)
            if isinstance(new_option, (FormInteger, FormNumber)) and existing_option:
                existing_option.minimum = min(
                    existing_option.minimum if existing_option.minimum is not None else float('-inf'),
                    new_option.minimum if new_option.minimum is not None else float('-inf')
                )
                existing_option.maximum = max(existing_option.maximum or float('inf'), new_option.maximum or float('inf'))
            elif not existing_option:
                self.possible_options[question_id].add(new_option)

    @staticmethod
    def _get_data_options(data_type, data_property):
        """Return options based on the given data type and property."""
        if data_type == "boolean":
            return {True, False}
        elif data_type == "integer":
            return {FormInteger(data_property.get("minimum"), data_property.get("maximum"))}
        elif data_type == "number":
            return {FormNumber(data_property.get("minimum"), data_property.get("maximum"))}
        elif data_type == "null":
            return {None}
        elif data_type == "string":
            return FormDefinition._handle_string_format(data_property)
        else:
            raise ValueError(f"Unsupported data type '{data_type}'")

    @staticmethod
    def _handle_string_format(data_property):
        """Handle specific string formats and return corresponding options."""
        if "format" in data_property and data_property["format"] == "date":
            return {FormDate()}
        elif "format" in data_property and data_property["format"] == "time":
            return {FormTime()}
        elif "format" in data_property and data_property["format"] == "date-time":
            return {FormDateTime()}
        elif "enum" in data_property:
            enum_options = set()
            for op in data_property["enum"]:
                enum_options.add(op)
            return enum_options
        else:
            return {FormString()}

    def validate_report(self, report, required_fields_validation=True, used_ids=None):
        """
        Validate a report against the schema, defined questions and defined resq dataset structure.

        Args:
            report (dict): The report to validate, in the format of wp4 resq data report structure (dataset["data"][k]).
            required_fields_validation (bool): Whether to validate the structure (required fields etc..) of JSON schema. Defaults to True.
            used_qa_ids (set): A set of already used question-answer IDs in different reports to check for duplicates. Defaults to None.

        Raises:
            Exception: If validation fails at any point.
        """
        used_ids = used_ids or set()
        if len(report["paragraphs"]) != 1:
            raise ValueError(f"Report must contain exactly 1 paragraph, found {len(report['paragraphs'])}.")

        paragraph = report["paragraphs"][0]
        context = paragraph["context"]
        
        # Validate question-answer pairs and their ids
        for qa in paragraph["qas"]:
            self._validate_qa(qa, report, used_ids)

        # Validate evidence text against the context
        for qa in paragraph["qas"]:
            self._validate_evidences(qa, context)

        # Validate resq form values against possible options
        for qa in paragraph["qas"]:
            self._validate_enumeration_value_ids(qa)

        # Validate against JSON schema if requested to check the structure correctness (required fields etc..)
        if required_fields_validation:
            self._validate_against_schema(paragraph)

    def _validate_qa(self, qa, report, used_ids):
        """Validate question-answer pairs for duplicates and ID format."""
        expected_id = f"{report['report_id']}_{qa['question_id']}"
        if qa["id"] != expected_id:
            raise ValueError(f"Question ID '{qa['id']}' does not match expected format '{expected_id}'.")
        if qa["id"] in used_ids:
            raise ValueError(f"Duplicate question ID '{qa['id']}' in report '{report['report_id']}'.")
        if qa["question_id"] not in self.question_ids:
            raise ValueError(f"Question ID '{qa['question_id']}' is not defined in the schema.")
        used_ids.add(qa["id"])

    def _validate_evidences(self, qa, context):
        """Validate the evidences for correct types and substring matches."""
        for answer in qa["answers"]:
            if answer["answer_type"] == "single":
                self._validate_single_answer(answer, context)
            elif answer["answer_type"] == "complex":
                self._validate_complex_answer(answer, context)
            else:
                raise ValueError(f"Unsupported answer type '{answer['answer_type']}'. Only 'single' or 'complex' are allowed.")

    def _validate_single_answer(self, answer, context):
        """Validate a single answer's format and presence in context."""
        text = answer["text"]
        start = answer["answer_start"]
        if not isinstance(text, str) or not isinstance(start, int):
            raise ValueError(f"Answer text '{text}' must be a string and start '{start}' must be an integer.")
        if not (len(text) >= 1 and start >= 0):
            raise ValueError(f"Answer text '{text}' must be non-empty and start index '{start}' must be valid.")
        if context[start:start + len(text)] != text:
            raise ValueError(f"Answer text '{text}' not found in context at position '{start}'.")

    def _validate_complex_answer(self, answer, context):
        """Validate a complex answer's format and substring matches."""
        if not isinstance(answer["text"], list) or not isinstance(answer["answer_start"], list):
            raise ValueError(f"Complex answer text '{answer['text']}' and start indices '{answer['answer_start']}' must be arrays.")
        if len(answer["text"]) != len(answer["answer_start"]) or len(answer["text"]) <= 1:
            raise ValueError(f"Text '{answer['text']}' and start '{answer['answer_start']}' arrays must be of the same length and contain more than one entry.")
        for text, start in zip(answer["text"], answer["answer_start"]):
            self._validate_single_answer({"text": text, "answer_start": start}, context)

    def _validate_enumeration_value_ids(self, qa):
        """Validate that the answer values fall within the acceptable options."""
        is_valid = any(
            qa["enumeration_value_id"] == op or (isinstance(op, (FormNumber, FormInteger, FormDate, FormDateTime, FormTime, FormString)) and op.is_valid(qa["enumeration_value_id"]))
            for op in self.possible_options[qa["question_id"]]
        )
        
        if not is_valid:
            valid_options = [str(pos_op) for pos_op in self.possible_options[qa["question_id"]]]
            raise ValueError(f"Answer '{qa['enumeration_value_id']}' is not valid for question ID '{qa['question_id']}'. Use one of '{valid_options}'")

    def _validate_against_schema(self, paragraph):
        """Validate the answers against the JSON schema."""
        resq_form_answers = {}
        for qa in paragraph["qas"]:
            parts = qa["question_id"].split(".")
            current = resq_form_answers
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = qa["enumeration_value_id"]
        validate(instance=resq_form_answers, schema=self.schema)

    def validate_dataset(self, dataset, required_fields_validation=True):
        """
        Validate a dataset of reports against the JSON schema, defined questions and defined resq dataset structure.

        Args:
            data (dict): The dataset containing multiple reports, in the format of wp4 resq dataset structure.
            required_fields_validation (bool): Whether to validate the structure (required fields etc..) of JSON schema. Defaults to True.
        """
        used_ids = set()
        invalid_report_count = 0
        for report in dataset["data"]:
            try:
                self.validate_report(report, required_fields_validation, used_ids)
            except ValidationError as e:
                invalid_report_count += 1
                logging.error(f"Report '{report['report_id']}' is NOT valid: {e.message}")
            except ValueError as e:
                invalid_report_count += 1
                logging.error(f"Report '{report['report_id']}' is NOT valid: {str(e)}")
        logging.info(f"{invalid_report_count}/{len(dataset['data'])} reports were invalid.")

    def question_includes_datatype(self, question_id: str, dtype: str):
        """
        Checks if the specified data type is included in the options for a given question ID.

        Args:
            question_id (str): The identifier for the question whose options are being checked.
            dtype (str): The data type to check for, which can be "boolean", "null", "enum", "integer", "number", "string", "date", "time" or "date-time".

        Returns:
            bool: True if the specified data type is present in the options for the question ID, otherwise False.
        """
        if dtype == "boolean": 
            return True in self.possible_options[question_id] or False in self.possible_options[question_id]
        elif dtype == "null": 
            return None in self.possible_options[question_id]
        elif dtype == "enum":
            return any([isinstance(op, str) for op in self.possible_options[question_id]])
        else:
            return any(
                isinstance(op, (FormNumber, FormDate, FormInteger, FormDateTime, FormTime, FormString)) and op.data_type == dtype
                for op in self.possible_options[question_id]
            )


class FormDate:
    data_type = "date"
    
    def __init__(self):
        pass

    def __str__(self):
        return "FormDate"

    def is_valid(self, var):
        try:
            return isinstance(var, str) and datetime.strptime(var, "%Y-%m-%d")
        except ValueError:
            return False

class FormDateTime:
    data_type = "date-time"
    
    def __init__(self):
        pass

    def __str__(self):
        return "FormDateTime"

    def is_valid(self, var):
        if not isinstance(var, str):
            return False

        formats = [
            "%Y-%m-%dT%H:%M:%S"
        ]

        for fmt in formats:
            try:
                datetime.strptime(var, fmt)
                return True
            except ValueError:
                continue

        return False


class FormInteger:
    data_type = "integer"
    
    def __init__(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    def __str__(self):
        return f"FormInteger(minimum {self.minimum}, maximum {self.maximum})"

    def is_valid(self, var):
        if isinstance(var, int):
            return (self.minimum is None or var >= self.minimum) and (self.maximum is None or var <= self.maximum)
        return False


class FormNumber:
    data_type = "number"
    
    def __init__(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    def __str__(self):
        return f"FormNumber(minimum {self.minimum}, maximum {self.maximum})"

    def is_valid(self, var):
        if isinstance(var, (float, int)):
            return (self.minimum is None or var >= self.minimum) and (self.maximum is None or var <= self.maximum)
        return False


class FormString:
    data_type = "string"
    
    def __init__(self):
        pass

    def __str__(self):
        return "FormString"

    def is_valid(self, var):
        return isinstance(var, str)


class FormTime:
    data_type = "time"
    
    def __init__(self):
        pass

    def __str__(self):
        return "FormTime"

    def is_valid(self, var):
        if not isinstance(var, str):
            return False

        formats = ["%H:%M:%S"]
        for fmt in formats:
            try:
                datetime.strptime(var, fmt)
                return True
            except ValueError:
                continue

        return False