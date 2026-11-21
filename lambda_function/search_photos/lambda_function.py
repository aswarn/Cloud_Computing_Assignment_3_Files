
import json
import os
import re
import uuid
import boto3

from opensearchpy import (
    OpenSearch,
    RequestsHttpConnection,
    AWSV4SignerAuth
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

REGION = os.environ.get("AWS_REGION", "us-east-1")

BOT_ID = os.environ.get("LEX_BOT_ID", "EHALDMPJDF")
BOT_ALIAS_ID = os.environ.get("LEX_BOT_ALIAS_ID", "TSTALIASID")
LOCALE_ID = os.environ.get("LEX_LOCALE_ID", "en_US")

OPENSEARCH_HOST = os.environ.get(
    "OPENSEARCH_HOST",
    "search-photos-assignment3-ullwvnlsdzjfqnhkdzh7y5zeaq.us-east-1.es.amazonaws.com"
)

# AWS clients
lex = boto3.client("lexv2-runtime", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

# OpenSearch authentication
credentials = boto3.Session().get_credentials()

auth = AWSV4SignerAuth(
    credentials,
    REGION,
    "es"
)

# OpenSearch connection
client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)


# --------------------------------------------------
# TEXT PROCESSING
# --------------------------------------------------

def singularize(word):
    """
    Convert common plural words into singular form.
    """

    irregular = {
        "people": "person",
        "men": "man",
        "women": "woman",
        "children": "child",
        "mice": "mouse",
        "geese": "goose",
        "feet": "foot",
        "teeth": "tooth"
    }

    if word in irregular:
        return irregular[word]

    # Examples: cities -> city, puppies -> puppy
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"

    # Examples: boxes -> box, dishes -> dish
    if word.endswith(("ches", "shes", "xes", "zes")):
        return word[:-2]

    # Examples: mountains -> mountain, birds -> bird
    if word.endswith("s") and not word.endswith(
        ("ss", "us", "is")
    ):
        return word[:-1]

    return word


def extract_search_terms(search_text):
    """
    Extract meaningful search terms from the full Lex query.
    """

    stopwords = {
        "show", "me", "find", "get", "display",
        "photos", "photo",
        "pictures", "picture",
        "images", "image",
        "with", "of", "the",
        "a", "an", "in", "on",
        "and", "or",
        "that", "have", "has",
        "containing", "containing",
        "where", "there", "are",
        "some", "all", "any",
        "please", "can", "you"
    }

    words = re.findall(
        r"[a-zA-Z]+",
        search_text.lower()
    )

    search_terms = []

    for word in words:

        if word in stopwords:
            continue

        term = singularize(word)

        if term not in search_terms:
            search_terms.append(term)

    return search_terms


# --------------------------------------------------
# LAMBDA HANDLER
# --------------------------------------------------

def lambda_handler(event, context):

    # ----------------------------------------------
    # 1. EXTRACT USER QUERY FROM API GATEWAY
    # ----------------------------------------------

    query_params = event.get("queryStringParameters") or {}

    q = query_params.get("q", "").strip()

    print("Original search query:", q)

    if not q:
        return response(200, [])

    # ----------------------------------------------
    # 2. SEND FULL QUERY TO AMAZON LEX
    # ----------------------------------------------

    lex_response = lex.recognize_text(
        botId=BOT_ID,
        botAliasId=BOT_ALIAS_ID,
        localeId=LOCALE_ID,
        sessionId=str(uuid.uuid4()),
        text=q
    )

    print(
        "LEX RESPONSE:",
        json.dumps(lex_response, default=str)
    )

    # ----------------------------------------------
    # 3. EXTRACT INTENT AND SLOTS
    # ----------------------------------------------

    intent = lex_response.get(
        "sessionState", {}
    ).get("intent", {})

    print("INTENT NAME:", intent.get("name"))
    print("INTENT STATE:", intent.get("state"))

    slots = intent.get("slots", {})

    print(
        "LEX SLOTS:",
        json.dumps(slots, default=str)
    )

    query_slot = slots.get("query")

    if not query_slot:
        print("No query slot returned by Lex")
        return response(200, [])

    # ----------------------------------------------
    # 4. EXTRACT SEARCH TEXT FROM LEX
    # ----------------------------------------------

    search_text = (
        query_slot.get("value", {}).get("interpretedValue")
        or query_slot.get("value", {}).get("originalValue")
    )

    if not search_text:
        print("No search text found in Lex query slot")
        return response(200, [])

    print("LEX SEARCH TEXT:", search_text)

    # ----------------------------------------------
    # 5. EXTRACT AND NORMALIZE SEARCH TERMS
    # ----------------------------------------------

    search_terms = extract_search_terms(search_text)

    print("EXTRACTED SEARCH TERMS:", search_terms)

    if not search_terms:
        print("No valid search terms extracted")
        return response(200, [])

    # ----------------------------------------------
    # 6. BUILD OPENSEARCH SQL QUERY
    # ----------------------------------------------

    conditions = []

    for term in search_terms:

        safe_term = term.replace("'", "''")

        conditions.append(
            f"MATCH(labels, '{safe_term}')"
        )

    # OR: Return photos matching at least one term
    where_clause = " AND ".join(conditions)

    sql_query = f"""
        SELECT bucket, objectKey, labels, createdTimestamp
        FROM photos
        WHERE {where_clause}
    """

    print("SQL QUERY:", sql_query)

    # ----------------------------------------------
    # 7. EXECUTE OPENSEARCH SQL QUERY
    # ----------------------------------------------

    opensearch_response = client.transport.perform_request(
        "POST",
        "/_plugins/_sql",
        body={
            "query": sql_query
        }
    )

    print(
        "SQL RESPONSE:",
        json.dumps(opensearch_response, default=str)
    )

    # ----------------------------------------------
    # 8. CONVERT SQL RESULTS INTO DICTIONARIES
    # ----------------------------------------------

    schema = [
        column["name"]
        for column in opensearch_response["schema"]
    ]

    results = []
    seen_keys = set()

    for row in opensearch_response.get("datarows", []):

        photo = dict(zip(schema, row))

        object_key = photo.get("objectKey")
        bucket_name = photo.get("bucket")

        # Avoid duplicate photos
        if not object_key or object_key in seen_keys:
            continue

        # ------------------------------------------
        # 9. GENERATE PRESIGNED S3 URL
        # ------------------------------------------

        image_url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket_name,
                "Key": object_key
            },
            ExpiresIn=3600
        )

        photo["url"] = image_url

        results.append(photo)

        seen_keys.add(object_key)

    print(
        "FINAL RESULTS:",
        json.dumps(results, default=str)
    )

    # ----------------------------------------------
    # 10. RETURN RESULTS
    # ----------------------------------------------

    return response(200, results)


# --------------------------------------------------
# API RESPONSE
# --------------------------------------------------

def response(status_code, results):

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "results": results
        }, default=str)
    }
