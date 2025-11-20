"""EC2 instance diagnostics utilities for debugging GPU pipeline failures."""


def capture_instance_diagnostics(ec2, instance_id):
    """Capture comprehensive diagnostics when EC2 instance fails to start.
    
    Args:
        ec2: boto3 EC2 client
        instance_id: EC2 instance ID to diagnose
        
    Returns:
        dict: Diagnostics including state, state_reason, status checks, and console output
    """
    diagnostics = {}
    try:
        # Get instance state and reason
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        diagnostics["state"] = instance["State"]["Name"]
        diagnostics["state_reason"] = instance.get("StateReason", {})
        diagnostics["state_transition_reason"] = instance.get("StateTransitionReason", "")
        
        # Get instance status checks
        status_response = ec2.describe_instance_status(
            InstanceIds=[instance_id], 
            IncludeAllInstances=True
        )
        if status_response.get("InstanceStatuses"):
            status = status_response["InstanceStatuses"][0]
            diagnostics["instance_status"] = status.get("InstanceStatus", {})
            diagnostics["system_status"] = status.get("SystemStatus", {})
        
        # Get console output (critical for boot failures)
        try:
            console_response = ec2.get_console_output(InstanceId=instance_id, Latest=True)
            console_output = console_response.get("Output", "")
            # Store first and last 2000 chars (boot and shutdown messages)
            if console_output:
                diagnostics["console_output_start"] = console_output[:2000]
                diagnostics["console_output_end"] = console_output[-2000:] if len(console_output) > 2000 else ""
                diagnostics["console_output_length"] = len(console_output)
        except Exception as e:
            diagnostics["console_output_error"] = str(e)
            
    except Exception as e:
        diagnostics["diagnostics_error"] = str(e)
    
    return diagnostics
