const { ECSClient, RunTaskCommand } = require("@aws-sdk/client-ecs");

const ecs = new ECSClient({ region: process.env.AWS_REGION ?? "eu-west-2" });

exports.handler = async (event) => {
  const records = event.Records ?? [];
  console.log(`Received ${records.length} SQS record(s)`);

  const results = [];

  for (const record of records) {
    try {
      const body = JSON.parse(record.body);
      const result = await triggerEcsTask(body);
      results.push(result);
    } catch (error) {
      console.error(`Failed to process record ${record.messageId}:`, error);
      throw error;
    }
  }

  return { triggered: results.length, tasks: results };
};

async function triggerEcsTask(body) {
  const { bucket, key, documentId } = body;
  console.log(`Triggering ECS task for documentId=${documentId}`);

  const response = await ecs.send(
    new RunTaskCommand({
      cluster: process.env.ECS_CLUSTER,
      taskDefinition: process.env.ECS_TASK_DEFINITION,
      launchType: "FARGATE",
      networkConfiguration: {
        awsvpcConfiguration: {
          subnets: process.env.SUBNETS.split(","),
          securityGroups: process.env.SECURITY_GROUPS.split(","),
          assignPublicIp: process.env.ASSIGN_PUBLIC_IP ?? "ENABLED",
        },
      },
      overrides: {
        containerOverrides: [
          {
            name: process.env.ECS_CONTAINER_NAME,
            environment: [
              { name: "BUCKET", value: bucket },
              { name: "KEY", value: key },
              { name: "DOCUMENT_ID", value: documentId },
            ],
          },
        ],
      },
    }),
  );

  if (response.failures?.length) {
    throw new Error(
      `ECS RunTask failed for ${documentId}: ${JSON.stringify(response.failures)}`,
    );
  }

  const taskArn = response.tasks?.[0]?.taskArn;
  if (!taskArn) {
    throw new Error(`ECS RunTask returned no task ARN for ${documentId}`);
  }

  console.log(`ECS task started: ${taskArn}`);
  return { documentId, taskArn };
}
