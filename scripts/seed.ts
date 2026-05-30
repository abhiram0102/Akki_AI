import { Pool, neonConfig } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-serverless";
import ws from "ws";
import { users } from "../shared/schema";
import bcrypt from "bcryptjs";

async function main() {
  neonConfig.webSocketConstructor = ws;
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  const db = drizzle({ client: pool, schema: { users } });

  const all = await db.select().from(users);
  console.log("Existing users:", all.map((u) => `${u.email} (${u.username})`));

  await db.delete(users);
  console.log("Cleared all users");

  const hash = await bcrypt.hash("Admin@123", 12);
  const [user] = await db.insert(users).values({
    email: "admin@akki.ai",
    username: "admin",
    password: hash,
    role: "owner",
    preferences: {},
    emotionalState: {
      bondLevel: 0,
      currentMood: "neutral",
      trustLevel: 0.5,
      personalityTraits: [],
      preferredCommunicationStyle: "professional",
    },
  }).returning();

  console.log("Seeded admin:", user.email, "id:", user.id);
  await pool.end();
}

main().catch((e) => { console.error(e); process.exit(1); });
