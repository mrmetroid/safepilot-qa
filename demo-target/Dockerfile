# Harbor Roast demo target: static files served by busybox httpd on :8081.
FROM busybox:1.36
COPY site /www
USER 65534
EXPOSE 8081
CMD ["httpd", "-f", "-v", "-p", "8081", "-h", "/www"]
