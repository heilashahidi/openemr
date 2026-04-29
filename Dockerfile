FROM php:8.3-apache

RUN apt-get update && apt-get install -y \
    libpng-dev libxml2-dev libzip-dev libonig-dev libcurl4-openssl-dev \
    unzip git && \
    docker-php-ext-install pdo pdo_mysql mysqli mbstring xml gd soap intl zip curl opcache

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html
COPY . .

RUN mkdir -p library/classes && \
    COMPOSER_ALLOW_SUPERUSER=1 composer install --optimize-autoloader --no-scripts --no-interaction

RUN a2enmod rewrite
EXPOSE 80

CMD ["apache2-foreground"]
