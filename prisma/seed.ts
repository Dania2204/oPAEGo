import { hash } from "bcryptjs";
import { PrismaClient, UserRole } from "@prisma/client";

const prisma = new PrismaClient();

async function seedUser(email: string, name: string, role: UserRole, password: string) {
  const passwordHash = await hash(password, 10);
  return prisma.user.upsert({
    where: { email },
    update: { name, role, passwordHash },
    create: { email, name, role, passwordHash }
  });
}

async function main() {
  const admin = await seedUser("admin@paego.local", "Admin Alcaldia", "ADMIN", "Admin123!");
  const driverUser = await seedUser("driver@paego.local", "Conductor Principal", "DRIVER", "Driver123!");
  const schoolUser = await seedUser("user@paego.local", "Colegio San Gabriel", "USER", "User123!");

  await prisma.driver.upsert({
    where: { userId: driverUser.id },
    update: {
      vehicleType: "Moto",
      phone: "3000000000",
      isAvailable: true
    },
    create: {
      userId: driverUser.id,
      vehicleType: "Moto",
      phone: "3000000000",
      isAvailable: true
    }
  });

  await prisma.school.upsert({
    where: { userId: schoolUser.id },
    update: {
      name: "Colegio Distrital San Gabriel",
      address: "Bogota"
    },
    create: {
      userId: schoolUser.id,
      name: "Colegio Distrital San Gabriel",
      address: "Bogota"
    }
  });

  console.log("Usuarios seed:");
  console.log("ADMIN  admin@paego.local / Admin123!");
  console.log("DRIVER driver@paego.local / Driver123!");
  console.log("USER   user@paego.local / User123!");
  console.log(`Admin id: ${admin.id}`);
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
