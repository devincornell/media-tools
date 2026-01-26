Getting your GTX 1080 Ti to play nice with a Dockerized upscaler on Ubuntu involves a few "non-standard" steps, particularly around Vulkan drivers.

Here is your streamlined, "single-source-of-truth" guide to rebuilding this system from scratch.

---

## Phase 1: Host System Preparation

Before touching Docker, your Ubuntu host must be ready to "share" its hardware.

### 1. Install NVIDIA Drivers

Ensure you have the proprietary drivers. For a 1080 Ti, version 535 or 550 is ideal.

```bash
sudo ubuntu-drivers autoinstall
# Reboot after installation
sudo reboot

```

### 2. Install the NVIDIA Container Toolkit

This is what allows Docker to "see" the GPU. Since it's not in the default Ubuntu repos, you must add the NVIDIA repository.

```bash
# Add the GPG key and Repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install the toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use the NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

```

### 3. Fix Permissions (No more sudo)

To run your upscales without typing `sudo` every time:

```bash
sudo usermod -aG docker $USER
# Activate the group change in your current shell
newgrp docker

```

---

## Phase 2: The "Magic" Command Structure

The hurdles we hit were mostly due to **Vulkan ICD** mapping. Video2X (the C++ version) needs to know exactly where your GPU's Vulkan configuration lives on the host.

### The "Universal" Upscale Command

Use this exact template for any future video.

```bash
docker run --rm -it \
  --runtime=nvidia \
  --gpus all \
  --privileged \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v /usr/share/vulkan/icd.d:/usr/share/vulkan/icd.d:ro \
  -v "$PWD":/host \
  ghcr.io/k4yt3x/video2x:latest \
  -i "/host/YOUR_INPUT.mp4" \
  -o "/host/YOUR_OUTPUT.mp4" \
  -p realesrgan \
  --realesrgan-model realesr-animevideov3 \
  -s 2 -d 0

```

---

## Phase 3: Troubleshooting Checklist

If you set this up on a new machine and it fails, check these three things in order:

1. **Driver Mismatch:** Run `nvidia-smi`. If the "CUDA Version" in the top right is lower than what the container expects, use an older image tag (e.g., `nvidia/cuda:12.2-base`).
2. **Vulkan Fallback:** If the logs say `Using Vulkan device: llvmpipe`, it means the `-v /usr/share/vulkan/icd.d...` mount isn't finding your driver files. Double-check that path on your host.
3. **Model Errors:** If a model like `realesrgan-plus-anime` fails, it's often because the Docker build only includes the `v3` models. Stick to `realesr-animevideov3` for the best balance of speed and compatibility.

---

### Your New Workflow

1. Put your videos in a folder.
2. Open **tmux** (so you can disconnect while it runs).
3. Run your script using the command above.
4. Press `Ctrl+B` then `D` to detach and let the 1080 Ti do its work.

**Would you like me to help you create a permanent `.bashrc` alias so you can just type `upscale movie.mp4` to trigger that entire long Docker command?**