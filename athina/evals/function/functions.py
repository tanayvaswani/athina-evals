import os
import re
import json
import requests
from typing import Any, Dict, Optional, Union
from athina.evals.grounded.similarity import CosineSimilarity
from athina.helpers.logger import logger
from athina.errors.exceptions import NoOpenAiApiKeyException
from athina.helpers.json import extract_json_path, validate_json
from athina.keys.openai_api_key import OpenAiApiKey
from athina.llms.openai_service import OpenAiService


def _standardize_url(url):
    """
    Generate a standardized URL by adding 'http://' if it's missing.

    Args:
        url (str): The input URL to be standardized.

    Returns:
        str: The standardized URL.
    """
    if url.startswith("http://") or url.startswith("https://"):
        return url
    else:
        return "http://" + url


def _preprocess_strings(keywords, text, case_sensitive):
    """
    Preprocess the keywords based on the case_sensitive flag.

    Args:
        keywords (str or List[str]): The keyword(s) to preprocess.
        case_sensitive (bool): Whether the preprocessing should be case-sensitive.

    Returns:
        List[str]: The preprocessed keywords.
    """
    # If keywords is a string, convert it to a list
    if isinstance(keywords, str):
        keywords = keywords.split(",")

    # Strip leading and spaces from the keywords
    keywords = list(map(lambda k: k.strip(), keywords))

    # If case_sensitive is False, convert all keywords and text to lowercase
    if not case_sensitive:
        keywords = [keyword.lower() for keyword in keywords]
        text = text.lower()

    return keywords, text


def regex(pattern, text, **kwargs):
    """
    Perform a regex search on the text and return a dictionary indicating whether the pattern was found.

    Args:
        pattern (str): The regex pattern to search for.
        text (str): The text string to search within.

    Returns:
        dict: A dictionary containing the result of the regex search and the reason for the result.
    """
    match = re.search(pattern, text)
    if match:
        return {"result": True, "reason": f"regex pattern {pattern} found in output"}
    else:
        return {
            "result": False,
            "reason": f"regex pattern {pattern} not found in output",
        }


def contains_any(keywords, text: str, case_sensitive=False, **kwargs):
    """
    Check if any of the provided keywords are present in the text.

    Args:
        keywords (str or List[str]): The keyword(s) to search for in the text.
        text (str): The text string to search within.
        case_sensitive (bool, optional): Whether the search should be case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the search and the reason for the result.
    """
    keywords, text = _preprocess_strings(keywords, text, case_sensitive)
    found_keywords = []
    for keyword in keywords:
        if keyword in text:
            found_keywords.append(keyword)

    if found_keywords:
        result = True
        reason = f"One or more keywords were found in output: " + ", ".join(
            found_keywords
        )
    else:
        result = False
        reason = "No keywords found in output"

    return {"result": result, "reason": reason}


def contains_all(keywords, text, case_sensitive=False, **kwargs):
    """
    Check if all the provided keywords are present in the text.

    Args:
        keywords (List[str]): The list of keywords to search for in the text.
        text (str): The text string to search within.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the keyword search and the reason for the result.
    """
    keywords, text = _preprocess_strings(keywords, text, case_sensitive)
    missing_keywords = []
    for keyword in keywords:
        if keyword not in text:
            result = False
            missing_keywords.append(keyword)
    if (len(missing_keywords)) > 0:
        result = False
        reason = f"keywords not found in output: " + ", ".join(missing_keywords)
    else:
        result = True
        reason = f"{len(keywords)}/{len(keywords)} keywords found in output"

    return {"result": result, "reason": reason}


def contains(keyword, text, case_sensitive=False, **kwargs):
    """
    Check if the text contains a specific keyword.

    Args:
        keyword (str): The keyword to search for in the text.
        text (str): The text string to search within.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the keyword search and the reason for the result.
    """
    if case_sensitive == False:
        text = text.lower()
        keyword = keyword.lower()
    if keyword not in text:
        result = False
        reason = f"keyword not found in output: " + keyword
    else:
        result = True
        reason = f"keyword {keyword} found in output"

    return {"result": result, "reason": reason}


def contains_none(keywords, text, case_sensitive=False, **kwargs):
    """
    Check if none of the provided keywords are present in the text.

    Args:
        keywords (str or List[str]): The keyword(s) to search for in the text.
        text (str): The text string to search within.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the check and the reason for the result.
    """
    keywords, text = _preprocess_strings(keywords, text, case_sensitive)
    found_keywords = []
    for keyword in keywords:
        if keyword in text:
            found_keywords.append(keyword)

    if found_keywords:
        result = False
        reason = f"One or more keywords were found in output: " + ", ".join(
            found_keywords
        )
    else:
        result = True
        reason = "No keywords found in output"

    return {"result": result, "reason": reason}


def contains_json(text, **kwargs):
    """
    Check if the text contains valid JSON.

    Args:
        text (str): The text string to check for valid JSON.

    Returns:
        dict: A dictionary containing the result of the JSON check and the reason for the result.
    """
    trimmed_output = text.strip()
    pattern = (
        r'\{(?:\s*"(?:\\.|[^"\\])*"\s*:\s*(?:"(?:\\.|[^"\\])*"|[^{}\[\]:,]+)|[^{}]+)*\}'
    )
    matches = re.findall(pattern, trimmed_output)

    if matches:
        results = []
        errors = []
        for potential_json_string in matches:
            try:
                parsed_json = json.loads(potential_json_string)
                results.append({"json": parsed_json, "valid": True})
            except json.JSONDecodeError as e:
                errors.append(
                    {"json": potential_json_string, "valid": False, "error": str(e)}
                )
        if errors:
            return {
                "result": False,
                "reason": "Output contains a potential JSON but it is invalid",
                "matches": results,
                "errors": errors,
            }
        else:
            return {
                "result": True,
                "reason": "Output contains JSON",
                "matches": results,
            }
    else:
        return {"result": False, "reason": "Output does not contain JSON"}


def contains_email(text, **kwargs):
    """
    Check if the text contains an email address.

    Args:
        text (str): The text string to check for an email address.

    Returns:
        dict: A dictionary containing the result of the email address check and the reason for the result.
    """
    return regex(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)


def is_json(text, **kwargs):
    """
    Check if the text contains valid JSON.

    Args:
        text (str): The text string to check for valid JSON.

    Returns:
        dict: A dictionary containing the result of the JSON check and the reason for the result.
    """
    try:
        json.loads(text)
        result = True
    except json.JSONDecodeError:
        result = False
    if result:
        return {
            "result": True,
            "reason": "Output contains JSON",
        }
    else:
        return {
            "result": False,
            "reason": "Output does not contain JSON",
        }


def is_email(text, **kwargs):
    """
    Check if the text is a valid email address.

    Args:
        text (str): The text string to check for a valid email address.

    Returns:
        dict: A dictionary containing the result of the email address check and the reason for the result.
    """
    return regex(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", text)


def contains_link(text, **kwargs):
    """
    Check if the text contains a link.

    Args:
        text (str): The text string to check for a link.

    Returns:
        dict: A dictionary containing the result of the link check and the reason for the result.
    """
    pattern = r"(?!.*@)(?:https?://)?(?:www\.)?\S+\.\S+"
    result = bool(re.search(pattern, text))
    if result:
        return {"result": True, "reason": "Link found in output"}
    else:
        return {"result": False, "reason": "No link found in output"}


def contains_valid_link(text, **kwargs):
    """
    Check if the text contains a valid link.

    Args:
        text (str): The text string to check for a valid link.

    Returns:
        dict: A dictionary containing the result of the link check and the reason for the result.
    """
    pattern = r"(?!.*@)(?:https?://)?(?:www\.)?\S+\.\S+"
    link_match = re.search(pattern=pattern, string=text)
    if link_match:
        matched_url = link_match.group()
        if matched_url:
            standardized_url = _standardize_url(matched_url)
            try:
                text = requests.head(standardized_url)
                if text.status_code == 200:
                    return {
                        "result": True,
                        "reason": f"link {matched_url} found in output and is valid",
                    }
                else:
                    return {
                        "result": False,
                        "reason": f"link {matched_url} found in output but is invalid",
                    }
            except:
                return {
                    "result": False,
                    "reason": f"link {matched_url} found in output but is invalid",
                }
    return {"result": False, "reason": f"no link found in output"}


def no_invalid_links(text, **kwargs):
    """
    Check for invalid links in the text.

    Args:
        text (str): The text string to check for invalid links.

    Returns:
        dict: A dictionary containing the result of the link check and the reason for the result.
    """
    pattern = r"(?!.*@)(?:https?://)?(?:www\.)?\S+\.\S+"
    link_match = re.search(pattern=pattern, string=text)
    if link_match:
        matched_url = link_match.group()
        if matched_url:
            standardized_url = _standardize_url(matched_url)
            try:
                text = requests.head(standardized_url)
                if text.status_code == 200:
                    return {
                        "result": True,
                        "reason": f"link {matched_url} found in output and is valid",
                    }
                else:
                    return {
                        "result": False,
                        "reason": f"link {matched_url} found in output but is invalid",
                    }
            except:
                return {
                    "result": False,
                    "reason": f"link {matched_url} found in output but is invalid",
                }
    return {"result": True, "reason": f"no invalid link found in output"}


def api_call(
    url: str,
    response: str,
    query: Optional[str] = None,
    context: Optional[str] = None,
    expected_response: Optional[str] = None,
    payload: dict = None,
    headers: dict = None,
):
    """
    Make an API call with payload to the specified URL.

    Args:
        url (str): The URL to make the API call to.
        text (str): The text to be added to the payload.
        query (Optional[str]): The query parameter to be added to the payload.
        context (Optional[str]): The context parameter to be added to the payload.
        expected_response (Optional[str]): The expected text parameter to be added to the payload.
        payload (dict, optional): The payload to be sent in the API call. Defaults to None.
        headers (dict, optional): The headers to be included in the API call. Defaults to None.

    Returns:
        dict: A dictionary containing the result and reason of the API call.
    """
    if payload is None:
        payload = {}
    if headers is None:
        headers = {}
    payload["response"] = response
    if query:
        payload["query"] = query
    if context:
        payload["context"] = context
    if expected_response:
        payload["expected_response"] = expected_response
    # Check the status code and set the reason accordingly
    try:
        api_response = requests.post(url, json=payload, headers=headers)
        if api_response.status_code == 200:
            # Success
            result = api_response.json().get("result")
            reason = api_response.json().get("reason")
        elif api_response.status_code == 400:
            # Bad Request
            result = False
            reason = "Bad Request: The server could not understand the request due to invalid syntax."
        elif api_response.status_code == 401:
            # Unauthorized
            result = False
            reason = "Unauthorized: Authentication is required and has failed or has not been provided."
        elif api_response.status_code == 500:
            # Internal Server Error
            result = False
            reason = (
                "Internal Server Error: The server encountered an unexpected condition."
            )
        else:
            # Other error codes
            result = False
            reason = f"An error occurred: {api_response.status_code}"
    except Exception as e:
        # Handle any exceptions that occur during the API call
        result = False
        reason = f"API Request Exception: {e}"

    return {"result": result, "reason": reason}


def equals(expected_text, text, case_sensitive=False, **kwargs):
    """
    Check if the text exactly matches the expected text.

    Args:
        expected_text (str): The expected text to compare against.
        text (str): The text to compare with the expected output.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result and reason of the comparison.
    """
    if case_sensitive == False:
        text = text.lower()
        expected_text = expected_text.lower()
    if text == expected_text:
        result = True
        reason = "✅ Text exactly matches expected text"
    else:
        result = False
        reason = "output does not exactly match expected text"
    return {"result": result, "reason": reason}


def starts_with(substring, text, case_sensitive=False, **kwargs):
    """
    Check if the text starts with a specified substring.

    Args:
        substring (str): The substring to check for at the start of the text.
        text (str): The text string to check.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the check and the reason for the result.
    """
    if case_sensitive == False:
        text = text.lower()
        substring = substring.lower()
    result = text.startswith(substring)
    if result == True:
        return {"result": result, "reason": "output starts with " + substring}
    else:
        return {"result": result, "reason": "output does not start with " + substring}


def ends_with(substring, text, case_sensitive=False, **kwargs):
    """
    Check if the text ends with a specified substring.

    Args:
        substring (str): The substring to check for at the end of the text.
        text (str): The text string to check.
        case_sensitive (bool, optional): If True, the comparison is case-sensitive. Defaults to False.

    Returns:
        dict: A dictionary containing the result of the check and the reason for the result.
    """
    if case_sensitive == False:
        text = text.lower()
        substring = substring.lower()
    result = text.endswith(substring)
    if result == True:
        return {"result": result, "reason": "output ends with " + substring}
    else:
        return {"result": result, "reason": "output does not end with " + substring}


def length_less_than(max_length, text, **kwargs):
    """
    Check if the length of the text is less than a specified maximum length.

    Args:
        max_length (int): The maximum length that the text should have.
        text (str): The text string to check the length of.

    Returns:
        dict: A dictionary containing the result of the length check and the reason for the result.
    """
    if len(text) < max_length:
        return {
            "result": True,
            "reason": f"output length is less than {max_length} characters",
        }
    else:
        return {
            "result": False,
            "reason": f"output length is greater than {max_length} characters",
        }


def length_greater_than(min_length, text, **kwargs):
    """
    Check if the length of the text is greater than a specified minimum length.

    Args:
        min_length (int): The minimum length that the text should have.
        text (str): The text string to check the length of.

    Returns:
        dict: A dictionary containing the result of the length check and the reason for the result.
    """
    if len(text) > min_length:
        return {
            "result": True,
            "reason": f"output length is greater than {min_length} characters",
        }
    else:
        return {
            "result": False,
            "reason": f"output length is less than {min_length} characters",
        }

def length_between(min_length, max_length, text, **kwargs):
    """
    Check if the length of the text is between a specified minimum and maximum length.

    Args:
        min_length (int): The minimum length that the text should have.
        max_length (int): The maximum length that the text should have.
        text (str): The text string to check the length of.

    Returns:
        dict: A dictionary containing the result of the length check and the reason for the result.
    """
    if min_length <= len(text) <= max_length:
        return {
            "result": True,
            "reason": f"output length is between {min_length} and {max_length} characters",
        }
    else:
        return {
            "result": False,
            "reason": f"output length is not between {min_length} and {max_length} characters",
        }

def one_line(text, **kwargs):
    """
    Check if the text is a single line.

    Args:
        text (str): The text string to check.

    Returns:
        dict: A dictionary containing the result of the check and the reason for the result.
    """
    if "\n" in text or len(text.splitlines()) > 1:
        return {"result": False, "reason": "output contains multiple lines"}
    else:
        return {"result": True, "reason": "output is a single line"}

def json_eval(
    actual_json: Union[dict, str],
    expected_json: Union[dict, str],
    **kwargs
) -> Dict[str, Any]:
    """
    Check if the actual JSON and expected JSON match the schema definition and follow validation rules.

    Args:
        actual_json (dict or str): The actual JSON string to compare against the expected JSON.
        expected_json (dict or str): The expected JSON string to compare against the actual JSON.

    """
    try:
        actual_json = _load_json(actual_json)
        expected_json = _load_json(expected_json)
        schema = _get_schema(kwargs)

        if not schema:
            return {"result": False, "reason": "Schema not provided"}

        if not (_validate_json_with_schema(actual_json, schema) and _validate_json_with_schema(expected_json, schema)):
            return {"result": False, "reason": "Schema validation failed"}

        validations = kwargs.get("validations", [])
        if validations:
            for validation in validations:
                if not _apply_validation(actual_json, expected_json, validation):
                    return {"result": False, "reason": "Validation failed"}

        return {"result": True, "reason": "Json eval passed"}
    except Exception as e:
        logger.error(f"Error occurred during eval: {e}")
        raise e

def _load_json(json_data: Union[dict, str]) -> dict:
    if isinstance(json_data, str):
        return json.loads(json_data)
    return json_data

def _get_schema(kwargs: Dict[str, Any]) -> dict:
    schema = kwargs.get("schema")
    if schema and isinstance(schema, str):
        return json.loads(schema.replace("\n", "").replace("\t", ""))
    return schema

def _validate_json_with_schema(json_data: dict, schema: dict) -> bool:
    return validate_json(json_data, schema)

def _apply_validation(actual_json: dict, expected_json: dict, validation: dict) -> bool:
    validating_function = validation.get("validating_function")
    json_path = validation.get("json_path")
    actual_value = extract_json_path(actual_json, json_path)
    expected_value = extract_json_path(expected_json, json_path)

    if validating_function == "Equals":
        return _validate_equals(actual_value, expected_value, json_path)
    elif validating_function == "Cosine Similarity":
        return _validate_cosine_similarity(actual_value, expected_value, validation)
    elif validating_function == "LLM Similarity":
        return _validate_llm_similarity(actual_value, expected_value, validation)
    else:
        logger.error(f"Validation function {validating_function} not supported")
        return False

def _validate_equals(actual_value: Any, expected_value: Any, json_path: str) -> bool:
    if actual_value != expected_value:
        logger.error(f"JSON path {json_path} does not match expected value")
        return False
    return True

def _validate_cosine_similarity(actual_value: str, expected_value: str, validation: dict) -> bool:
    threshold = validation.get("pass_threshold", 0.8)
    cosine_similarity = CosineSimilarity().compare(str(actual_value), str(expected_value))
    if cosine_similarity < threshold:
        logger.error(f"Cosine similarity score {cosine_similarity} is less than the threshold {threshold}")
        return False
    return True

def _validate_llm_similarity(actual_value: str, expected_value: str, validation: dict) -> bool:
    open_ai_api_key = validation.get("open_ai_api_key") or OpenAiApiKey.get_key() or os.environ.get("OPENAI_API_KEY")
    if not open_ai_api_key:
        raise NoOpenAiApiKeyException()

    OpenAiApiKey.set_key(open_ai_api_key)
    llm_service = OpenAiService()

    system_message = """
    You are an expert at evaluating whether two given strings are similar or not. Consider semantic similarity also while evaluating.
    You MUST return a JSON object with the following fields: 
    - result: Result must be either 'Pass' or 'Fail'.
    - explanation: An explanation of why the result is Pass or Fail.
    - score: Any matching score you have used to come to the result.
    """

    user_message = f"""
    Following are two strings:
    1. String 1: {actual_value}.
    2. String 2: {expected_value}.
    """

    response = llm_service.json_completion(
        model=validation.get("model", "gpt-3.5-turbo"),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )

    try:
        result = response["result"]
        explanation = response["explanation"]
        if result == "Fail":
            logger.error(f"LLM Similarity validation failed: {explanation}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error occurred during LLM similarity validation: {e}")
        return False

# def json_eval(actual_json, expected_json, **kwargs):
#     """
#     Check if the actual JSON and expected JSON match the schema definition and follow validation rules.

#     Args:
#         actual_json (dict or str): The actual JSON string to compare against the expected JSON.
#         expected_json (dict or str): The expected JSON string to compare against the actual JSON.

#     """
#     try:
#         if isinstance(actual_json, str):
#             actual_json = json.loads(actual_json)
#         if isinstance(expected_json, str):
#             expected_json = json.loads(expected_json)
#         # Extract the schema from the kwargs
#         schema = kwargs.get("schema", None)
#         if schema is None:
#             return {
#                 "result": False,
#                 "reason": "Schema not provided",
#             }
#         if isinstance(schema, str):
#             schema = schema.replace("\n", "").replace("\t", "")
#             schema_json = json.loads(schema)
#         else:
#             schema_json = schema
#         # validate_json using the schema
#         actual_json_valid = validate_json(actual_json, schema_json)
#         expected_json_valid = validate_json(expected_json, schema_json)
#         # If either the expected or actual JSON is invalid, return False
#         if not actual_json_valid or not expected_json_valid:
#             return {
#                 "result": False,
#                 "reason": "Schema validation failed",
#             }
#         validations = kwargs.get("validations", []) 
#         if validations:
#             for validation in validations:
#                 validating_function = validation.get("validating_function")
#                 json_path = validation.get("json_path")
#                 actual_value = extract_json_path(actual_json, json_path)
#                 expected_value = extract_json_path(expected_json, json_path)
#                 if validating_function == "Equals":
#                     if actual_value != expected_value:
#                         return {
#                             "result": False,
#                             "reason": f"JSON path {json_path} does not match expected value",
#                         }
#                 elif validating_function == "Cosine Similarity":
#                     consine_similarity_threshold = validation.get("pass_threshold", 0.8)
#                     cosine_similarity = CosineSimilarity()
#                     cosine_similarity_value = cosine_similarity.compare(str(actual_value), str(expected_value))
#                     if cosine_similarity_value < consine_similarity_threshold:
#                         return {
#                             "result": False,
#                             "reason": f"JSON path {json_path} cosine similarity score is {round(cosine_similarity_value, 2)} which is less than the threshold {consine_similarity_threshold}",
#                         }
#                 elif validating_function == "LLM Similarity":
#                     open_ai_api_key = validation.get("open_ai_api_key", None)
#                     if open_ai_api_key is None:
#                         if OpenAiApiKey.get_key() is None:
#                             open_ai_api_key = os.environ.get("OPENAI_API_KEY", None)
#                             if open_ai_api_key is None:
#                                 raise NoOpenAiApiKeyException()
#                             OpenAiApiKey.set_key(open_ai_api_key)
#                     else:
#                         OpenAiApiKey.set_key(open_ai_api_key)
#                     llm_service = OpenAiService()

#                     SYSTEM_MESSAGE_TEMPLATE = """ 
#                     You are an expert at evaluating whether two given strings are similar or not. Consider semantic similarity also while evaluating.
#                     You MUST return a JSON object with the following fields: 
#                     - result: Result must be either 'Pass' or 'Fail'.
#                     - explanation: An explanation of why the result is Pass or Fail.
#                     - score: Any matching score you have used to come to the result.
#                     """

#                     USER_MESSAGE_TEMPLATE = """
#                         Following are two strings:
#                         1. String 1: {actual_value}.
#                         2. String 2: {expected_value}.
#                     """

#                     chat_completion_response_json: dict = llm_service.json_completion(
#                         model=kwargs.get("model", "gpt-3.5-turbo"),
#                         messages=[
#                             {
#                                 "role": "system",
#                                 "content": SYSTEM_MESSAGE_TEMPLATE,
#                             },
#                             {
#                                 "role": "user",
#                                 "content": USER_MESSAGE_TEMPLATE.format(actual_value=actual_value, expected_value=expected_value),
#                             },
#                         ],
#                         temperature=0.0,
#                     )
#                     try:
#                         result = chat_completion_response_json["result"]
#                         explanation = chat_completion_response_json["explanation"]
#                         failure = bool(result == "Fail")
#                         if failure:
#                             return {
#                                 "result": False,
#                                 "reason": explanation,
#                             }
#                     except Exception as e:
#                         logger.error(f"Error occurred during eval: {e}")
#                         raise e
#                 else:
#                     return {
#                         "result": False,
#                         "reason": "Validation function not supported",
#                     }
#         return {
#             "result": True,
#             "reason": "Json eval passed",
#         }
#     except Exception as e:
#         logger.error(f"Error occurred during eval: {e}")
#         raise e
   
"""
A dictionary containing the available operations and their corresponding functions.
"""
operations = {
    "Regex": regex,
    "ContainsAny": contains_any,
    "ContainsAll": contains_all,
    "Contains": contains,
    "ContainsNone": contains_none,
    "ContainsJson": contains_json,
    "ContainsEmail": contains_email,
    "IsJson": is_json,
    "IsEmail": is_email,
    "NoInvalidLinks": no_invalid_links,
    "ContainsLink": contains_link,
    "ContainsValidLink": contains_valid_link,
    "Equals": equals,
    "StartsWith": starts_with,
    "EndsWith": ends_with,
    "LengthLessThan": length_less_than,
    "LengthGreaterThan": length_greater_than,
    "LengthBetween": length_between,
    "ApiCall": api_call,
    "OneLine": one_line,
    "JsonEval": json_eval,
}
