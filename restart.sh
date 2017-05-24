docker-compose build legacy-livereplayserver
docker-compose stop legacy-livereplayserver
echo "y" | docker-compose rm legacy-livereplayserver
docker-compose up -d legacy-livereplayserver
