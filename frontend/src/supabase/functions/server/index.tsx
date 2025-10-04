import { Hono } from "npm:hono";
import { cors } from "npm:hono/cors";
import { logger } from "npm:hono/logger";
import * as kv from "./kv_store.tsx";
import { createClient } from "npm:@supabase/supabase-js@2";

const app = new Hono();

// Enable logger
app.use('*', logger(console.log));

// Enable CORS for all routes and methods
app.use(
  "/*",
  cors({
    origin: "*",
    allowHeaders: ["Content-Type", "Authorization"],
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    exposeHeaders: ["Content-Length"],
    maxAge: 600,
  }),
);

// Health check endpoint
app.get("/make-server-b652e8c8/health", (c) => {
  return c.json({ status: "ok" });
});

// Repository ingestion endpoint
app.post("/make-server-b652e8c8/ingest", async (c) => {
  try {
    // Get and verify access token
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      console.log('Ingestion error: No access token provided');
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
    );

    const { data: { user }, error: authError } = await supabase.auth.getUser(accessToken);
    
    if (authError || !user) {
      console.log('Ingestion error: Failed to authenticate user:', authError);
      return c.json({ error: 'Unauthorized' }, 401);
    }

    // Get request body
    const body = await c.req.json();
    const { repoUrl } = body;

    if (!repoUrl) {
      console.log('Ingestion error: No repository URL provided');
      return c.json({ error: 'Repository URL is required' }, 400);
    }

    // Validate GitHub URL
    const githubUrlPattern = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/;
    if (!githubUrlPattern.test(repoUrl.trim())) {
      console.log('Ingestion error: Invalid GitHub URL format:', repoUrl);
      return c.json({ error: 'Invalid GitHub repository URL' }, 400);
    }

    // Store ingestion job in KV store
    const jobId = crypto.randomUUID();
    const timestamp = new Date().toISOString();
    
    await kv.set(`ingestion:${jobId}`, {
      jobId,
      userId: user.id,
      userEmail: user.email,
      repoUrl,
      status: 'pending',
      createdAt: timestamp,
    });

    // Also track by user
    const userJobs = await kv.get(`user:${user.id}:jobs`) || [];
    userJobs.push(jobId);
    await kv.set(`user:${user.id}:jobs`, userJobs);

    console.log(`Repository ingestion job created: ${jobId} for user ${user.email}`);

    // In a real implementation, you would:
    // 1. Queue the job for processing
    // 2. Process the repository in the background
    // 3. Send an email notification when complete
    
    return c.json({ 
      success: true, 
      jobId,
      message: 'Repository submitted for ingestion',
      email: user.email 
    });
  } catch (error) {
    console.log('Server error during ingestion:', error);
    return c.json({ error: 'Internal server error' }, 500);
  }
});

// Get user's ingestion jobs
app.get("/make-server-b652e8c8/jobs", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      console.log('Get jobs error: No access token provided');
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
    );

    const { data: { user }, error: authError } = await supabase.auth.getUser(accessToken);
    
    if (authError || !user) {
      console.log('Get jobs error: Failed to authenticate user:', authError);
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const jobIds = await kv.get(`user:${user.id}:jobs`) || [];
    const jobs = [];
    
    for (const jobId of jobIds) {
      const job = await kv.get(`ingestion:${jobId}`);
      if (job) {
        jobs.push(job);
      }
    }

    return c.json({ jobs });
  } catch (error) {
    console.log('Server error getting jobs:', error);
    return c.json({ error: 'Internal server error' }, 500);
  }
});

Deno.serve(app.fetch);