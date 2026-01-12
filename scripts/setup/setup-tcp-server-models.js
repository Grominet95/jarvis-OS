import fs from 'node:fs'
import path from 'node:path'

import {
  PYTHON_TCP_SERVER_TTS_BERT_BASE_DIR_PATH,
  // PYTHON_TCP_SERVER_TTS_BERT_FRENCH_DIR_PATH,
  // PYTHON_TCP_SERVER_TTS_BERT_FRENCH_MODEL_HF_PREFIX_DOWNLOAD_URL,
  PYTHON_TCP_SERVER_TTS_MODEL_PATH,
  PYTHON_TCP_SERVER_ASR_MODEL_DIR_PATH,
  PYTHON_TCP_SERVER_TTS_MODEL_HF_DOWNLOAD_URL,
  PYTHON_TCP_SERVER_ASR_MODEL_HF_PREFIX_DOWNLOAD_URL,
  PYTHON_TCP_SERVER_TTS_BERT_BASE_MODEL_HF_PREFIX_DOWNLOAD_URL
} from '@/constants'
import { LogHelper } from '@/helpers/log-helper'
import { FileHelper } from '@/helpers/file-helper'
import { NetworkHelper } from '@/helpers/network-helper'

const ASR_MODEL_FILES = [
  'model.bin',
  'config.json',
  'preprocessor_config.json',
  'tokenizer.json',
  'vocabulary.json'
]
/*const TTS_BERT_FRENCH_MODEL_FILES = [
  'pytorch_model.bin', // Not needed? Compare with HF auto download in ~/.cache/huggingface/hub...
  'config.json',
  'vocab.txt',
  'tokenizer_config.json'
]*/
const TTS_BERT_BASE_MODEL_FILES = [
  'pytorch_model.bin',
  'config.json',
  'vocab.txt',
  'tokenizer_config.json',
  'tokenizer.json'
]

async function installTTSModel() {
  try {
    LogHelper.info('Installing TTS model...')

    const destPath = PYTHON_TCP_SERVER_TTS_MODEL_PATH

    LogHelper.info(`Downloading TTS model...`)

    const pythonTCPServerTTSModelDownloadURL =
      await NetworkHelper.setHuggingFaceURL(
        PYTHON_TCP_SERVER_TTS_MODEL_HF_DOWNLOAD_URL
      )

    await FileHelper.downloadFile(pythonTCPServerTTSModelDownloadURL, destPath)

    LogHelper.success(`TTS model downloaded at ${destPath}`)
  } catch (e) {
    LogHelper.error(`Failed to install TTS model: ${e}`)
    process.exit(1)
  }
}
async function installASRModel() {
  try {
    LogHelper.info('Installing ASR model...')

    for (const modelFile of ASR_MODEL_FILES) {
      const pythonTCPServerASRModelDownloadURL =
        await NetworkHelper.setHuggingFaceURL(
          PYTHON_TCP_SERVER_ASR_MODEL_HF_PREFIX_DOWNLOAD_URL
        )
      const modelInstallationFileURL = `${pythonTCPServerASRModelDownloadURL}/${modelFile}?download=true`
      const destPath = path.join(
        PYTHON_TCP_SERVER_ASR_MODEL_DIR_PATH,
        modelFile
      )

      LogHelper.info(`Downloading ${modelFile}...`)

      await FileHelper.downloadFile(modelInstallationFileURL, destPath)

      LogHelper.success(`${modelFile} downloaded at ${destPath}`)
    }

    LogHelper.success('ASR model installed')
  } catch (e) {
    LogHelper.error(`Failed to install ASR model: ${e}`)
    process.exit(1)
  }
}
/*async function installTTSBERTFrenchModel() {
  try {
    LogHelper.info('Installing TTS BERT French model...')

    for (const modelFile of TTS_BERT_FRENCH_MODEL_FILES) {
      const pythonTCPServerTTSBERTFrenchModelPrefixDownloadURL = await NetworkHelper.setHuggingFaceURL(
        PYTHON_TCP_SERVER_TTS_BERT_FRENCH_MODEL_HF_PREFIX_DOWNLOAD_URL
      )
      const modelInstallationFileURL = `${pythonTCPServerTTSBERTFrenchModelPrefixDownloadURL}/${modelFile}?download=true`
      const destPath = path.join(PYTHON_TCP_SERVER_TTS_BERT_FRENCH_DIR_PATH, modelFile)

      LogHelper.info(`Downloading ${modelFile}...`)

      await FileHelper.downloadFile(modelInstallationFileURL, destPath)

      LogHelper.success(`${modelFile} downloaded at ${destPath}`)
    }

    LogHelper.success('TTS BERT French model installed')
  } catch (e) {
    LogHelper.error(`Failed to install TTS BERT French model: ${e}`)
    process.exit(1)
  }
}*/
async function installTTSBERTBaseModel() {
  try {
    LogHelper.info('Installing TTS BERT base model...')

    for (const modelFile of TTS_BERT_BASE_MODEL_FILES) {
      const pythonTCPServerTTSBERTBaseModelPrefixDownloadURL =
        await NetworkHelper.setHuggingFaceURL(
          PYTHON_TCP_SERVER_TTS_BERT_BASE_MODEL_HF_PREFIX_DOWNLOAD_URL
        )
      const modelInstallationFileURL = `${pythonTCPServerTTSBERTBaseModelPrefixDownloadURL}/${modelFile}?download=true`
      const destPath = path.join(
        PYTHON_TCP_SERVER_TTS_BERT_BASE_DIR_PATH,
        modelFile
      )

      LogHelper.info(`Downloading ${modelFile}...`)

      await FileHelper.downloadFile(modelInstallationFileURL, destPath)

      LogHelper.success(`${modelFile} downloaded at ${destPath}`)
    }

    LogHelper.success('TTS BERT base model installed')
  } catch (e) {
    LogHelper.error(`Failed to install TTS BERT base model: ${e}`)
    process.exit(1)
  }
}

export default async () => {
  LogHelper.info(
    'Checking whether TTS BERT base language model files are downloaded...'
  )
  const areTTSBERTBaseFilesDownloaded = fs.existsSync(
    path.join(
      PYTHON_TCP_SERVER_TTS_BERT_BASE_DIR_PATH,
      TTS_BERT_BASE_MODEL_FILES[TTS_BERT_BASE_MODEL_FILES.length - 1]
    )
  )
  if (!areTTSBERTBaseFilesDownloaded) {
    LogHelper.info('TTS BERT base language model files not downloaded')
    await installTTSBERTBaseModel()
  } else {
    LogHelper.success(
      'TTS BERT base language model files are already downloaded'
    )
  }

  // TODO: later when multiple languages are supported
  /*LogHelper.info(
    'Checking whether TTS BERT French language model files are downloaded...'
  )
  const areTTSBERTFrenchFilesDownloaded = fs.existsSync(
    path.join(
      PYTHON_TCP_SERVER_TTS_BERT_FRENCH_DIR_PATH,
      TTS_BERT_FRENCH_MODEL_FILES[TTS_BERT_FRENCH_MODEL_FILES.length - 1]
    )
  )
  if (!areTTSBERTFrenchFilesDownloaded) {
    LogHelper.info('TTS BERT French language model files not downloaded')
    await installTTSBERTFrenchModel()
  } else {
    LogHelper.success(
      'TTS BERT French language model files are already downloaded'
    )
  }*/

  LogHelper.info('Checking whether the TTS model is installed...')
  const isTTSModelInstalled = fs.existsSync(PYTHON_TCP_SERVER_TTS_MODEL_PATH)
  if (!isTTSModelInstalled) {
    LogHelper.info('TTS model is not installed')
    await installTTSModel()
  } else {
    LogHelper.success('TTS model is already installed')
  }

  LogHelper.info('Checking whether the ASR model is installed...')
  // Check if model.bin file exists in directory (last file in the list)
  const isASRModelInstalled = fs.existsSync(
    path.join(
      PYTHON_TCP_SERVER_ASR_MODEL_DIR_PATH,
      ASR_MODEL_FILES[ASR_MODEL_FILES.length - 1]
    )
  )
  if (!isASRModelInstalled) {
    LogHelper.info('ASR model is not installed')
    await installASRModel()
  } else {
    LogHelper.success('ASR model is already installed')
  }
}
