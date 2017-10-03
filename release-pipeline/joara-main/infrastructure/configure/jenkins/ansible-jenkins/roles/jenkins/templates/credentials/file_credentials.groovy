#!/usr/bin/env groovy

import com.cloudbees.plugins.credentials.*;
import com.cloudbees.plugins.credentials.domains.Domain;
import org.jenkinsci.plugins.plaincredentials.impl.FileCredentialsImpl;
import java.nio.file.*;

Path fileLocation = Paths.get("/var/lib/jenkins/.ssh/id_rsa");

def secretBytes = SecretBytes.fromBytes(Files.readAllBytes(fileLocation))
def credentials = new FileCredentialsImpl(CredentialsScope.GLOBAL, 'acs_private_key', 'acs private key', 'id_rsa', secretBytes)

SystemCredentialsProvider.instance.store.addCredentials(Domain.global(), credentials)