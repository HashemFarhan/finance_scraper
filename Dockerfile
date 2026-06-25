FROM public.ecr.aws/lambda/python:3.12

# Chromium + its OS libraries, plus the runtime deps. boto3 is NOT bundled in
# container-image Lambdas (only in the managed zip runtimes), so install it here.
RUN pip install --no-cache-dir playwright boto3 openai \
    && playwright install --with-deps chromium

# Playwright installs the browser under /root/.cache by default during build,
# but Lambda runs as a non-root user, so pin the browser path to a baked-in,
# read-only location that the function can reach at runtime.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright playwright install chromium

COPY . ${LAMBDA_TASK_ROOT}

# Default command; each Lambda created from this image can override it.
CMD ["handlers.worker.handler"]
