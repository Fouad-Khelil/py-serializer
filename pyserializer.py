import json
import logging
from typing import TypedDict, IO


class CompanyData(TypedDict):
    CONFORMED_NAME: str
    CIK: str
    ASSIGNED_SIC: str
    ORGANIZATION_NAME: str
    IRS_NUMBER: str
    STATE_OF_INCORPORATION: str
    FISCAL_YEAR_END: str


class FilingValues(TypedDict):
    FORM_TYPE: str
    ACT: str
    FILE_NUMBER: str
    FILM_NUMBER: str


class Address(TypedDict):
    STREET1: str
    CITY: str
    STATE: str
    ZIP: str
    PHONE: str


class MailAddress(TypedDict):
    STREET1: str
    CITY: str
    STATE: str
    ZIP: str


class FormerCompany(TypedDict):
    FORMER_CONFORMED_NAME: str
    DATE_CHANGED: str


class Filer(TypedDict):
    COMPANY_DATA: CompanyData
    FILING_VALUES: FilingValues
    BUSINESS_ADDRESS: Address
    MAIL_ADDRESS: MailAddress
    FORMER_COMPANY: list[FormerCompany]


class Document(TypedDict):
    TYPE: str
    SEQUENCE: str
    FILENAME: str
    DESCRIPTION: str


class Submission(TypedDict):
    ACCESSION_NUMBER: str
    TYPE: str
    PUBLIC_DOCUMENT_COUNT: str
    PERIOD: str
    ITEMS: list[str]
    FILING_DATE: str
    DATE_OF_FILING_DATE_CHANGE: str
    FILER: list[Filer]
    DOCUMENT: list[Document]


def deserialize(input: IO[str]) -> Submission:
    """
    Processes the sec filing and returns a dictionary representing the data.

    Args:
        input_data: the sec filing as IO object (open() or StringIO)

    Returns:
        A dictionary representing the processed data.
    """
    try:
        # Read the first line
        first_line = input.readline()
        if not first_line.startswith(("<SUBMISSION>", "<SEC-DOCUMENT>")):
            raise ValueError(
                "Invalid file format, expected <SUBMISSION> or <SEC-DOCUMENT> at the start of the file")

        fields: Submission = {}
        process_nested_fields("SUBMISSION", fields, input)

        # Test if the output is correct
        expected_top_fields = ["DOCUMENT", "FILER"]
        for field in expected_top_fields:
            if field not in fields:
                logging.warning(f"Warning: top level Field '{
                                field}' not found in the file: {input.name}")

        return fields
    except Exception as e:
        logging.error(f"Error processing input: {e}")
        raise


def process_nested_fields(field_name: str, fields: dict[str, any], reader: IO[str]) -> None:
    while True:
        line = reader.readline()
        if not line:
            break  # End of file

        # End of parent field
        if line.startswith((f"</{field_name}>", "</SEC-DOCUMENT>")):
            return

        # Split the line into key and value
        if not line.startswith('<'):
            raise ValueError(
                f"Invalid line format, expected '<' at start of line, in line: {line}")

        parts = line.split('>', 1)
        if len(parts) < 2:
            raise ValueError(
                f"Invalid line format, expected '>' in line: {line}")

        key = parts[0][1:].strip()
        value = parts[1].strip()

        if key == "TEXT":
            content = []
            while True:
                line = reader.readline()
                if not line:
                    raise ValueError(
                        "Unexpected end of file while reading TEXT field")

                if line.startswith("</TEXT>"):
                    fields[key] = ''.join(content)
                    break
                else:
                    content.append(line)
        elif key == "SEC-HEADER":
            processTxtHeader(fields, reader)
        elif not value and key not in ["ORGANIZATION-NAME", "CONFIRMING-COPY", "PRIVATE-TO-PUBLIC", "CORRECTION", "DELETION"]:
            # Nested field
            if field_is_array(key):
                if key not in fields:
                    fields[key] = []
                new_parent = {}
                fields[key].append(new_parent)
                process_nested_fields(key, new_parent, reader)
            else:
                if key in fields:
                    raise ValueError(f"Duplicate key found in the file: {key}")
                new_parent = {}
                fields[key] = new_parent
                process_nested_fields(key, new_parent, reader)
        else:
            if field_is_array(key):
                if key not in fields:
                    fields[key] = []
                fields[key].append(value)
            else:
                if key in fields:
                    raise ValueError(f"Duplicate key found in the file: {key}")
                fields[key] = value


KEY_MAP = {
    # Top-level submission keys
    "ACCESSION NUMBER": "ACCESSION-NUMBER",
    "CONFORMED SUBMISSION TYPE": "TYPE",
    "PUBLIC DOCUMENT COUNT": "PUBLIC-DOCUMENT-COUNT",
    "CONFORMED PERIOD OF REPORT": "PERIOD",
    # "ITEM INFORMATION": "ITEMS", # not compatible, in .nc they are decimal values, in .txt they are text
    "FILED AS OF DATE": "FILING-DATE",
    "DATE AS OF CHANGE": "DATE-OF-FILING-DATE-CHANGE",

    "FILER": ("FILER", {
        "COMPANY DATA": ("COMPANY-DATA", {
            "COMPANY CONFORMED NAME": "CONFORMED-NAME",
            "CENTRAL INDEX KEY": "CIK",
            "STANDARD INDUSTRIAL CLASSIFICATION": "ASSIGNED-SIC",
            "ORGANIZATION NAME": "ORGANIZATION-NAME",
            "IRS NUMBER": "IRS-NUMBER",
            "STATE OF INCORPORATION": "STATE-OF-INCORPORATION",
            "FISCAL YEAR END": "FISCAL-YEAR-END",
        }),
        "FILING VALUES": ("FILING-VALUES", {
            "FORM TYPE": "FORM-TYPE",
            "SEC ACT": "ACT",
            "SEC FILE NUMBER": "FILE-NUMBER",
            "FILM NUMBER": "FILM-NUMBER",
        }),
        "BUSINESS ADDRESS": ("BUSINESS-ADDRESS", {
            "STREET 1": "STREET1",
            "CITY": "CITY",
            "STATE": "STATE",
            "ZIP": "ZIP",
            "BUSINESS PHONE": "PHONE",
        }),
        "MAIL ADDRESS": ("MAIL-ADDRESS", {
            "STREET 1": "STREET1",
            "CITY": "CITY",
            "STATE": "STATE",
            "ZIP": "ZIP",
        }),
        "FORMER COMPANY": ("FORMER-COMPANY", {
            "FORMER CONFORMED NAME": "FORMER-CONFORMED-NAME",
            "DATE OF NAME CHANGE": "DATE-CHANGED",
        })
    }),
}


def processTxtHeader(fields: dict[str, any], reader: IO[str]) -> None:
    # 3rd element is the key of the current section, purely for logging
    current_section_stack = [(fields, KEY_MAP, "")]
    while len(current_section_stack) > 0:
        fields, key_map, _ = current_section_stack[-1]
        line = reader.readline()

        if not line or line.strip() == "":
            if len(fields.keys()) > 0 and len(current_section_stack) > 1:
                current_section_stack.pop()
            continue

        if line.startswith("</SEC-HEADER>"):
            break

        if line.startswith("<ACCEPTANCE-DATETIME>"):
            continue

        parts = line.split(':', 1)
        if len(parts) == 0:
            raise ValueError(
                f"Invalid line format in SEC-HEADER, expected ': in line: {line}")

        key = parts[0].strip()
        value = "" if len(parts) == 1 else parts[1].strip()

        if key in key_map:
            if isinstance(key_map[key], tuple):  # nested
                orig_key = key_map[key][0]
                if field_is_array(orig_key):
                    if orig_key not in fields:
                        fields[orig_key] = []
                    new_parent = {}
                    fields[orig_key].append(new_parent)
                    current_section_stack.append(
                        (new_parent, key_map[key][1], key))
                else:
                    if orig_key in fields:
                        logging.warning(
                            f"Duplicate key found in the file: {orig_key}")
                    new_parent = {}
                    fields[orig_key] = new_parent
                    current_section_stack.append(
                        (new_parent, key_map[key][1], key))

            else:  # simple value
                orig_key = key_map[key]
                if field_is_array(orig_key):
                    if orig_key not in fields:
                        fields[orig_key] = []
                    fields[orig_key].append(value)
                else:
                    if orig_key in fields:
                        logging.warning(
                            f"Duplicate key found in the file: {orig_key}")
                    fields[orig_key] = value
        elif not (not key or not value) and key != "ITEM INFORMATION":
            logging.warning(
                f"Unknown key in SEC-HEADER: key={key}, value={value}, section={current_section_stack[-1][2]}")


def field_is_array(field: str) -> bool:
    return field in [
        "ITEMS", "FORMER-COMPANY", "DOCUMENT", "CLASS-CONTRACT", "FORMER-NAME",
        "FILER", "SERIES", "GROUP-MEMBERS", "FILED-FOR", "REPORTING-OWNER",
        "NEW-SERIES", "MERGER", "ITEM", "REFERENCES-429", "TARGET-DATA", "NEW-CLASSES-CONTRACTS",
        "SUBJECT-COMPANY", "RULE"
    ]


# Example usage
# if __name__ == "__main__":
#     input_path = open("../0001045810-24-000028.txt", "r")
#     output = deserialize(input_path)
#     json.dump(output, open("output-txt.json", "w"), indent=4)
