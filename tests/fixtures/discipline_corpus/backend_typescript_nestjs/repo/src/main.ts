import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
async function bootstrap() { await NestFactory.create(AppModule); }
