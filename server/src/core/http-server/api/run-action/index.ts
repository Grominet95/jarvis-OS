import type { FastifyPluginAsync } from 'fastify'

import { runAction } from '@/core/http-server/api/run-action/post'
import type { APIOptions } from '@/core/http-server/http-server'

export const runActionPlugin: FastifyPluginAsync<APIOptions> = async (
  fastify,
  options
) => {
  // Execute a skill action
  await fastify.register(runAction, options)
}
