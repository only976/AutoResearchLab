import docker
import os
import logging
import shutil
from backend.utils.logger import setup_logger

class DockerSandbox:
    def __init__(self, image_name="autoresearchlab-sandbox"):
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Warning: Docker client initialization failed. Ensure Docker is running. Error: {e}")
            self.client = None
            
        self.image_name = image_name
        self.logger = setup_logger(self.__class__.__name__)

    def build_image(self):
        """Builds the sandbox docker image."""
        if not self.client:
            return False
            
        dockerfile_path = os.path.dirname(os.path.abspath(__file__))
        self.logger.info(f"Building docker image {self.image_name} from {dockerfile_path}...")
        try:
            self.client.images.build(
                path=dockerfile_path,
                tag=self.image_name,
                rm=True
            )
            self.logger.info("Image built successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to build image: {e}")
            return False

    def ensure_image(self):
        if not self.client:
            return False
        try:
            self.client.images.get(self.image_name)
            return True
        except docker.errors.ImageNotFound:
            self.logger.info("Image not found, building...")
            return self.build_image()
        except Exception as e:
            self.logger.error(f"Error checking image: {e}")
            return False

    def build_experiment_image(self, experiment_id, workspace_path):
        """
        Builds a custom Docker image for the experiment with pre-installed dependencies.
        """
        if not self.client:
            return None

        req_path = os.path.join(workspace_path, "requirements.txt")
        if not os.path.exists(req_path):
            self.logger.info("No requirements.txt found, using base image.")
            return self.image_name

        custom_image_tag = f"autoresearchlab/exp_{experiment_id.lower()}"
        
        # Create a temporary Dockerfile in the workspace
        dockerfile_path = os.path.join(workspace_path, "Dockerfile.exp")
        try:
            with open(dockerfile_path, "w") as f:
                f.write(f"""
FROM {self.image_name}
WORKDIR /home/researcher/workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
""")
            
            self.logger.info(f"Building custom image {custom_image_tag}...")
            # Use workspace_path as context
            self.client.images.build(
                path=workspace_path,
                dockerfile=dockerfile_path,
                tag=custom_image_tag,
                rm=True
            )
            self.logger.info(f"Custom image {custom_image_tag} built successfully.")
            return custom_image_tag
            
        except Exception as e:
            self.logger.error(f"Failed to build custom image: {e}")
            raise e
        finally:
            if os.path.exists(dockerfile_path):
                try:
                    os.remove(dockerfile_path)
                except:
                    pass

    def run_command(self, command: str, workspace_path: str, timeout=300, image_name=None):
        """
        Runs an arbitrary shell command in the sandbox.
        """
        if not self.client:
            return {"exit_code": -1, "stdout": "", "stderr": "Docker client not available. Is Docker running?"}

        os.makedirs(workspace_path, exist_ok=True)
        
        target_image = image_name if image_name else self.image_name
        
        container = None
        try:
            # If using base image, ensure it exists. Custom images are assumed to be built.
            if target_image == self.image_name:
                if not self.ensure_image():
                    return {"exit_code": -1, "stdout": "", "stderr": "Failed to prepare Docker image"}
            
            # For custom images, we should check if they exist too, but let's assume the build step succeeded.

            container = self.client.containers.run(
                target_image,
                command=f"/bin/bash -c '{command}'",
                volumes={workspace_path: {'bind': '/home/researcher/workspace', 'mode': 'rw'}},
                working_dir="/home/researcher/workspace",
                detach=True,
                network_mode="bridge",
                mem_limit="2g",
            )
            
            try:
                result = container.wait(timeout=timeout)
                exit_code = result["StatusCode"]
                logs = container.logs().decode("utf-8")
                return {"exit_code": exit_code, "stdout": logs, "stderr": ""}
            except Exception as e: # Timeout or other error
                try:
                    container.kill()
                except:
                    pass
                return {"exit_code": -1, "stdout": "", "stderr": f"Execution error: {str(e)}"}
                
        except Exception as e:
            return {"exit_code": -1, "stdout": "", "stderr": f"Container launch failed: {str(e)}"}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except:
                    pass

    def run_code(self, code: str, workspace_path: str, filename="script.py", timeout=300, image_name=None):
        """
        Runs python code in the sandbox.
        
        Args:
            code: The python code content.
            workspace_path: Absolute path to the local directory to mount.
            filename: Name of the file to create inside workspace.
            timeout: Execution timeout in seconds.
            image_name: Optional custom image tag to use.
            
        Returns:
            dict: {exit_code, stdout, stderr}
        """
        if not self.client:
            return {"exit_code": -1, "stdout": "", "stderr": "Docker client not available. Is Docker running?"}

        # Ensure workspace exists
        os.makedirs(workspace_path, exist_ok=True)
        
        target_image = image_name if image_name else self.image_name

        # Write code to file in workspace
        script_path = os.path.join(workspace_path, filename)
        with open(script_path, "w") as f:
            f.write(code)
            
        # Run container
        container = None
        try:
            if target_image == self.image_name:
                if not self.ensure_image():
                    return {"exit_code": -1, "stdout": "", "stderr": "Failed to prepare Docker image"}

            # Define resource limits
            host_config = self.client.api.create_host_config(
                binds={workspace_path: {'bind': '/home/researcher/workspace', 'mode': 'rw'}},
                mem_limit="2g",
                cpu_quota=100000 # 1 CPU roughly
            )

            # NOTE: We no longer auto-install requirements.txt here. 
            # It should be handled by build_experiment_image.
            
            full_command = f"python3 {filename}"

            container = self.client.containers.run(
                target_image,
                command=f"/bin/bash -c '{full_command}'",
                volumes={workspace_path: {'bind': '/home/researcher/workspace', 'mode': 'rw'}},
                working_dir="/home/researcher/workspace",
                detach=True,
                network_mode="bridge", # Allow internet access
                mem_limit="2g",
            )
            
            try:
                result = container.wait(timeout=timeout)
                exit_code = result["StatusCode"]
            except Exception as e:
                container.kill()
                return {"exit_code": -1, "stdout": "", "stderr": f"Timeout or execution error: {str(e)}"}

            logs = container.logs().decode("utf-8")
            
            return {
                "exit_code": exit_code,
                "stdout": logs,
                "stderr": "" # Docker logs combined
            }
            
        except Exception as e:
            return {
                "exit_code": -1, 
                "stdout": "", 
                "stderr": f"Execution failed: {str(e)}"
            }
        finally:
            if container:
                try:
                    container.remove(force=True)
                except:
                    pass

if __name__ == "__main__":
    # Simple Test
    import tempfile
    sandbox = DockerSandbox()
    if sandbox.client:
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"Testing in {tmpdir}")
            code = "import numpy as np; print(f'Numpy version: {np.__version__}')"
            res = sandbox.run_code(code, tmpdir)
            print("Result:", res)
    else:
        print("Skipping test, docker not ready.")
