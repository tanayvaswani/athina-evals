# Step to make an external api call
import json
import time
from typing import Union, Dict, Any, Iterable, Optional
import requests
from athina.steps import Step
from jinja2 import Environment
from athina.helpers.jinja_helper import PreserveUndefined


def prepare_input_data(data):
    return {key: json.dumps(value) if isinstance(value, (list, dict)) else value
        for key, value in data.items()}


class ApiCall(Step):
    """
    Step that makes an external API call.

    Attributes:
        url: The URL of the API endpoint to call.
        method: The HTTP method to use (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        headers: Optional headers to include in the API request.
        body: Optional request body to include in the API request.
    """

    url: str
    method: str
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, str]] = None
    body: Optional[str] = None
    env: Environment = None

    class Config:
        arbitrary_types_allowed = True

    def execute(self, input_data: Any) -> Union[Dict[str, Any], None]:
        """Make an API call and return the response."""

        if input_data is None:
            input_data = {}

        if not isinstance(input_data, dict):
            raise TypeError("Input data must be a dictionary.")

        # Create a custom Jinja2 environment with double curly brace delimiters and PreserveUndefined
        self.env = Environment(
            variable_start_string='{{', 
            variable_end_string='}}',
            undefined=PreserveUndefined
        )
        # Add a filter to the Jinja2 environment to convert the input data to JSON
        if self.body is not None:
            body_template = self.env.from_string(self.body)
            prepared_input_data = prepare_input_data(input_data)
            self.body = body_template.render(**prepared_input_data)
        
        if self.headers is not None:
            for key, value in self.headers.items():
                self.headers[key] = self.env.from_string(value).render(**prepared_input_data)

        if self.params is not None:
            for key, value in self.params.items():
                self.params[key] = self.env.from_string(value).render(**prepared_input_data)
                self.params[key] = requests.utils.quote(self.params[key])

        retries = 3  # number of retries
        timeout = 5  # seconds
        for attempt in range(retries):
            try:
                response = requests.request(
                    method=self.method,
                    url=self.url,
                    headers=self.headers,
                    params=self.params,
                    json=json.loads(self.body) if self.body else None,
                    timeout=timeout,
                )
                if response.status_code >= 400:
                    # If the status code is an error, return the error message
                    return {
                        "status": "error",
                        "data": f"Failed to make the API call.\nStatus code: {response.status_code}\nError:\n{response.text}",
                    }
                try:
                    json_response = response.json()
                    # If the response is JSON, return the JSON data
                    return {
                        "status": "success",
                        "data": json_response,
                    }
                except json.JSONDecodeError:
                    # If the response is not JSON, return the text
                    return {
                        "status": "success",
                        "data": response.text,
                    }
            except requests.Timeout:
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                # If the request times out after multiple attempts, return an error message
                return {
                    "status": "error",
                    "data": "Failed to make the API call.\nRequest timed out after multiple attempts.",
                }
            except Exception as e:
                # If an exception occurs, return the error message
                return {
                    "status": "error",
                    "data": f"Failed to make the API call.\nError: {e.__class__.__name__}\nDetails:\n{str(e)}",
                }
