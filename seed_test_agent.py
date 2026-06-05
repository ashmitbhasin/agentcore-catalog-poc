"""
seed_test_agent.py — Create a test Bedrock agent in your AWS account.
Run this ONCE before catalog.py to have something to pull.

Usage:
    python seed_test_agent.py --region us-east-1 --role-arn arn:aws:iam::123456789:role/YourBedrockRole

If you already have agents, skip this script entirely.
"""

import boto3
import argparse
import json
import time

def create_test_agent(region: str, role_arn: str, profile: str | None = None):
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    client = session.client("bedrock-agent", region_name=region)

    print("Creating test agent...")
    resp = client.create_agent(
        agentName="agentcore-catalog-test-agent",
        agentResourceRoleArn=role_arn,
        foundationModel="anthropic.claude-3-haiku-20240307-v1:0",
        description="Test agent created by agentcore-catalog-poc seed script.",
        instruction=(
            "You are a helpful assistant for internal tooling demos. "
            "Your purpose is to verify the AgentCore catalog connector works correctly."
        ),
        idleSessionTTLInSeconds=600,
    )

    agent = resp["agent"]
    agent_id = agent["agentId"]
    print(f"Created agent: {agent_id} ({agent['agentName']})")

    # Prepare the agent so status becomes PREPARED
    print("Preparing agent (this takes ~10s)...")
    client.prepare_agent(agentId=agent_id)
    time.sleep(10)

    detail = client.get_agent(agentId=agent_id)["agent"]
    print(f"Agent status: {detail['agentStatus']}")
    print(f"\nDone. Now run: python catalog.py --region {region}")
    return agent_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a test Bedrock agent")
    parser.add_argument("--region",   default="us-east-1")
    parser.add_argument("--role-arn", required=True, help="IAM role ARN for the agent")
    parser.add_argument("--profile",  default=None)
    args = parser.parse_args()

    create_test_agent(args.region, args.role_arn, args.profile)
