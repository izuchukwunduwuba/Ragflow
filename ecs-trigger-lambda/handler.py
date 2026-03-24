import json
import os
import logging
import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ecs = boto3.client("ecs", region_name=os.environ.get("AWS_REGION", "eu-west-2"))

ECS_CLUSTER = os.environ["ECS_CLUSTER"]
ECS_TASK_DEFINITION = os.environ["ECS_TASK_DEFINITION"]
ECS_CONTAINER_NAME = os.environ["ECS_CONTAINER_NAME"]
SUBNETS = os.environ["SUBNETS"].split(",")
SECURITY_GROUPS = os.environ["SECURITY_GROUPS"].split(",")
ASSIGN_PUBLIC_IP = os.environ.get("ASSIGN_PUBLIC_IP", "ENABLED")


def lambda_handler(event, context):
    records = event.get("Records", [])
    log.info("Received %d SQS record(s)", len(records))

    results = []
    for record in records:
        try:
            body = json.loads(record["body"])
            result = trigger_ecs_task(body)
            results.append(result)
        except Exception as e:
            log.error("Failed to process record: %s | error: %s", record.get("messageId"), e)
            raise

    return {"triggered": len(results), "tasks": results}


def trigger_ecs_task(body: dict) -> dict:
    bucket = body["bucket"]
    key = body["key"]
    document_id = body["documentId"]

    log.info("Triggering ECS task for documentId=%s", document_id)

    response = ecs.run_task(
        cluster=ECS_CLUSTER,
        taskDefinition=ECS_TASK_DEFINITION,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": SECURITY_GROUPS,
                "assignPublicIp": ASSIGN_PUBLIC_IP,
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": ECS_CONTAINER_NAME,
                    "environment": [
                        {"name": "BUCKET",      "value": bucket},
                        {"name": "KEY",         "value": key},
                        {"name": "DOCUMENT_ID", "value": document_id},
                    ],
                }
            ]
        },
    )

    failures = response.get("failures", [])
    if failures:
        raise RuntimeError(f"ECS RunTask failed for {document_id}: {failures}")

    task_arn = response["tasks"][0]["taskArn"]
    log.info("ECS task started: %s", task_arn)

    return {"documentId": document_id, "taskArn": task_arn}
